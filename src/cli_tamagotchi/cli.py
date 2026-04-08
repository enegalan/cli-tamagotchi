from __future__ import annotations

import argparse
import os
import select
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Sequence, TextIO

from rich.console import Console
from rich.live import Live
from rich.text import Text

from .engine import apply_action, create_new_pet, pick_random_pet_name, reconcile_state
from .models import PetState
from .render import _lights_action_name, render_interactive_view, render_status
from .storage import PetStorage

try:
    import termios
    import tty
except ImportError:  # pragma: no cover
    termios = None
    tty = None

SUPPORTED_ACTIONS = ("feed", "play", "lights", "clean", "medicine")
EVENT_WINDOW_SIZE = 6
NO_ACTION = "__no_action__"
IDLE_POLL_NO_INPUT = "idle_poll"
INTERACTIVE_IDLE_TIMEOUT_SECONDS = 0.3


def build_action_grid(pet_state: PetState, storage: PetStorage) -> tuple[tuple[str | None, str | None], ...]:
    if pet_state.is_alive:
        return (
            ("feed", "play"),
            (_lights_action_name(pet_state), "clean"),
            ("medicine", "quit"),
        )
    if storage.can_create_new_pet(pet_state):
        return (("new_pet", "quit"),)
    return (("quit", None),)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tama", description="Care for your terminal pet.")
    parser.add_argument(
        "--name",
        default=None,
        metavar="NAME",
        help="Pet name; skips the name prompt when creating. Empty value picks a random name.",
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("status", help="Show the current pet status.")
    subparsers.add_parser("feed", help="Feed your pet.")
    subparsers.add_parser("play", help="Play with your pet.")
    subparsers.add_parser("lights", help="Toggle the lights on or off.")
    subparsers.add_parser("clean", help="Clean your pet's space.")
    subparsers.add_parser("medicine", help="Give medicine (cooldown 1h, cures illness, restores health).")
    subparsers.add_parser("new", help="Start a new pet (only if none is alive).")
    return parser


def main(
    argv: Optional[list[str]] = None,
    storage: Optional[PetStorage] = None,
    now_provider: Optional[Callable[[], datetime]] = None,
    output: Optional[TextIO] = None,
    input_stream: Optional[TextIO] = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output = output or sys.stdout
    input_stream = input_stream or sys.stdin
    now_provider = now_provider or datetime.now
    storage = storage or PetStorage(base_dir=_storage_dir_from_env())
    console = Console(file=output, width=100)

    pet_state = load_or_create_pet(
        storage, now_provider(), args.name, output=output, input_stream=input_stream
    )

    if args.command == "new":
        if pet_state.is_alive:
            console.print("A pet is already alive. You can only have one living pet.", style="bold red")
            return 1
        new_name = name_from_flag_or_prompt(args.name, output, input_stream)
        pet_state = create_new_pet(now=now_provider(), name=new_name)
        storage.save(pet_state)
        console.print(f"A new pet, {pet_state.name}, has hatched.", style="bold green")
        console.print(render_status(pet_state, compact=True, animation_time=now_provider()))
        return 0

    if not args.command:
        return run_interactive_loop(
            pet_state=pet_state,
            storage=storage,
            now_provider=now_provider,
            console=console,
            output=output,
            input_stream=input_stream,
            explicit_pet_name=args.name,
        )

    if args.command == "status":
        storage.save(pet_state)
        console.print(render_status(pet_state, compact=True, animation_time=now_provider()))
        return 0

    result = apply_action(pet_state, args.command, now_provider())
    storage.save(result.pet_state)
    console.print(result.message, style="bold green")
    console.print(render_status(result.pet_state, compact=True, animation_time=now_provider()))
    return 0


def name_from_flag_or_prompt(
    explicit_flag: Optional[str],
    output: TextIO,
    input_stream: TextIO,
    *,
    live: Optional[Live] = None,
) -> str:
    if explicit_flag is not None:
        stripped_flag = explicit_flag.strip()
        return stripped_flag if stripped_flag else pick_random_pet_name()
    if live is not None:
        live.stop()
    try:
        return _prompt_pet_name_line(output, input_stream)
    finally:
        if live is not None:
            live.start(refresh=True)


def _prompt_pet_name_line(output: TextIO, input_stream: TextIO) -> str:
    input_is_tty = bool(getattr(input_stream, "isatty", lambda: False)())
    if not input_is_tty:
        return pick_random_pet_name()
    output.write("\nPet name (Enter for random): ")
    output.flush()
    line = input_stream.readline()
    if not line:
        return pick_random_pet_name()
    stripped_line = line.strip()
    return stripped_line if stripped_line else pick_random_pet_name()


def load_or_create_pet(
    storage: PetStorage,
    now: datetime,
    pet_name: Optional[str],
    *,
    output: TextIO,
    input_stream: TextIO,
) -> PetState:
    pet_state = storage.load()
    if pet_state is None:
        resolved_name = name_from_flag_or_prompt(pet_name, output, input_stream)
        pet_state = create_new_pet(now=now, name=resolved_name)
    else:
        reconcile_state(pet_state, now)

    storage.save(pet_state)
    return pet_state


def run_interactive_loop(
    pet_state: PetState,
    storage: PetStorage,
    now_provider: Callable[[], datetime],
    console: Console,
    output: TextIO,
    input_stream: TextIO,
    explicit_pet_name: Optional[str],
) -> int:
    status_message: Optional[Text] = None
    selected_position = (0, 0)
    event_offset = _default_event_offset(pet_state, EVENT_WINDOW_SIZE)
    if not _supports_fullscreen(output, input_stream):
        return _run_interactive_loop_fallback(
            pet_state=pet_state,
            storage=storage,
            now_provider=now_provider,
            console=console,
            output=output,
            input_stream=input_stream,
            explicit_pet_name=explicit_pet_name,
        )

    with Live(
        render_interactive_view(
            pet_state,
            _highlight_key_at_position(build_action_grid(pet_state, storage), selected_position),
            event_offset=event_offset,
            animation_time=now_provider(),
            action_rows=build_action_grid(pet_state, storage),
        ),
        console=console,
        screen=True,
        auto_refresh=False,
    ) as live:
        while True:
            current_time = now_provider()
            reconcile_state(pet_state, current_time)
            action_grid = build_action_grid(pet_state, storage)
            selected_position = _clamp_selection(action_grid, selected_position)
            live.update(
                render_interactive_view(
                    pet_state,
                    _highlight_key_at_position(action_grid, selected_position),
                    event_offset=event_offset,
                    status_message=status_message,
                    animation_time=current_time,
                    action_rows=action_grid,
                ),
                refresh=True,
            )

            raw_action = _read_action_input(
                output,
                input_stream,
                idle_timeout_seconds=INTERACTIVE_IDLE_TIMEOUT_SECONDS,
            )
            if raw_action is None:
                storage.save(pet_state)
                return 0
            if raw_action == NO_ACTION:
                continue

            if raw_action in ("up", "down", "left", "right"):
                selected_position = _move_selection(action_grid, selected_position, raw_action)
                continue
            if raw_action == "events_up":
                event_offset = _move_event_offset(pet_state, event_offset, EVENT_WINDOW_SIZE, -1)
                continue
            if raw_action == "events_down":
                event_offset = _move_event_offset(pet_state, event_offset, EVENT_WINDOW_SIZE, 1)
                continue
            if raw_action == "select":
                command = _command_from_grid_cell(
                    _grid_value_at_position(action_grid, selected_position)
                )
            else:
                command = _normalize_action_input(raw_action)
                if command is None:
                    status_message = Text("Unknown action.", style="bold red")
                    continue

            if command == "":
                status_message = Text("Select a highlighted action.", style="yellow")
                continue

            if command in ("quit", "exit"):
                storage.save(pet_state)
                live.update(
                    render_interactive_view(
                        pet_state,
                        _highlight_key_at_position(action_grid, selected_position),
                        event_offset=event_offset,
                        status_message=Text("Goodbye.", style="bold cyan"),
                        animation_time=now_provider(),
                        action_rows=action_grid,
                    ),
                    refresh=True,
                )
                return 0

            if command == "new_pet":
                if pet_state.is_alive:
                    status_message = Text("You already have a living pet.", style="bold red")
                    continue
                if not storage.can_create_new_pet(pet_state):
                    status_message = Text("Cannot start a new pet right now.", style="bold red")
                    continue
                hatch_name = name_from_flag_or_prompt(
                    explicit_pet_name, output, input_stream, live=live
                )
                pet_state = create_new_pet(now_provider(), hatch_name)
                storage.save(pet_state)
                event_offset = _default_event_offset(pet_state, EVENT_WINDOW_SIZE)
                selected_position = (0, 0)
                status_message = Text(f"{pet_state.name} hatched! A fresh start.", style="bold green")
                continue

            result = apply_action(pet_state, command, now_provider())
            pet_state = result.pet_state
            storage.save(pet_state)
            event_offset = _default_event_offset(pet_state, EVENT_WINDOW_SIZE)
            status_message = Text(result.message, style="bold green")


def _storage_dir_from_env() -> Optional[Path]:
    custom_home = os.environ.get("CLI_TAMAGOTCHI_HOME")
    if not custom_home:
        return None
    return Path(custom_home).expanduser()


def _supports_fullscreen(output: TextIO, input_stream: TextIO) -> bool:
    output_is_tty = bool(getattr(output, "isatty", lambda: False)())
    input_is_tty = bool(getattr(input_stream, "isatty", lambda: False)())
    return output_is_tty and input_is_tty


def _run_interactive_loop_fallback(
    pet_state: PetState,
    storage: PetStorage,
    now_provider: Callable[[], datetime],
    console: Console,
    output: TextIO,
    input_stream: TextIO,
    explicit_pet_name: Optional[str],
) -> int:
    status_message: Optional[Text] = None
    selected_position = (0, 0)
    event_offset = _default_event_offset(pet_state, EVENT_WINDOW_SIZE)

    while True:
        reconcile_state(pet_state, now_provider())
        action_grid = build_action_grid(pet_state, storage)
        selected_position = _clamp_selection(action_grid, selected_position)
        console.print(
            render_interactive_view(
                pet_state,
                _highlight_key_at_position(action_grid, selected_position),
                event_offset=event_offset,
                status_message=status_message,
                action_rows=action_grid,
            )
        )

        raw_action = _read_action_input(output, input_stream)
        if raw_action is None:
            storage.save(pet_state)
            return 0
        if raw_action == NO_ACTION:
            continue

        if raw_action == "events_up":
            event_offset = _move_event_offset(pet_state, event_offset, EVENT_WINDOW_SIZE, -1)
            continue
        if raw_action == "events_down":
            event_offset = _move_event_offset(pet_state, event_offset, EVENT_WINDOW_SIZE, 1)
            continue
        if raw_action == "select":
            command = _command_from_grid_cell(
                _grid_value_at_position(action_grid, selected_position)
            )
        else:
            command = _normalize_action_input(raw_action)
            if command is None:
                status_message = Text("Unknown action.", style="bold red")
                continue

        if command == "":
            status_message = Text("Select a highlighted action.", style="yellow")
            continue

        if command in ("quit", "exit"):
            storage.save(pet_state)
            console.print("Goodbye.", style="bold cyan")
            return 0

        if command == "new_pet":
            if pet_state.is_alive:
                status_message = Text("You already have a living pet.", style="bold red")
                continue
            if not storage.can_create_new_pet(pet_state):
                status_message = Text("Cannot start a new pet right now.", style="bold red")
                continue
            hatch_name = name_from_flag_or_prompt(explicit_pet_name, output, input_stream)
            pet_state = create_new_pet(now_provider(), hatch_name)
            storage.save(pet_state)
            event_offset = _default_event_offset(pet_state, EVENT_WINDOW_SIZE)
            selected_position = (0, 0)
            status_message = Text(f"{pet_state.name} hatched! A fresh start.", style="bold green")
            continue

        result = apply_action(pet_state, command, now_provider())
        pet_state = result.pet_state
        storage.save(pet_state)
        event_offset = _default_event_offset(pet_state, EVENT_WINDOW_SIZE)
        status_message = Text(result.message, style="bold green")


def _supports_single_key_input(input_stream: TextIO) -> bool:
    if termios is None or tty is None:
        return False

    input_is_tty = bool(getattr(input_stream, "isatty", lambda: False)())
    has_fileno = hasattr(input_stream, "fileno")
    return input_is_tty and has_fileno


def _read_action_input(
    output: TextIO,
    input_stream: TextIO,
    idle_timeout_seconds: Optional[float] = None,
) -> Optional[str]:
    if _supports_single_key_input(input_stream):
        single_key_action = _read_single_key(input_stream, idle_timeout_seconds=idle_timeout_seconds)
        if single_key_action == IDLE_POLL_NO_INPUT:
            return NO_ACTION
        if single_key_action is None:
            return NO_ACTION
        return single_key_action

    output.write("> ")
    output.flush()
    raw_command = input_stream.readline()
    if not raw_command:
        return None
    return raw_command


def _read_single_key(
    input_stream: TextIO,
    idle_timeout_seconds: Optional[float] = None,
) -> Optional[str]:
    file_descriptor = input_stream.fileno()
    previous_settings = termios.tcgetattr(file_descriptor)
    try:
        tty.setraw(file_descriptor)
        if idle_timeout_seconds is not None:
            ready_descriptors, _, _ = select.select([file_descriptor], [], [], idle_timeout_seconds)
            if not ready_descriptors:
                return IDLE_POLL_NO_INPUT
        pressed_key = _read_key_from_descriptor(file_descriptor)
        if not pressed_key:
            return None

        if pressed_key in ("\x03", "\x04"):
            return "quit"

        if pressed_key == "\x1b":
            next_character = _read_key_if_available(file_descriptor, 0.15)
            if not next_character:
                return None
            if next_character not in ("[", "O"):
                return None
            arrow_key = _read_key_if_available(file_descriptor, 0.15)
            if not arrow_key:
                return None
            if next_character == "O":
                return {
                    "A": "up",
                    "B": "down",
                    "C": "right",
                    "D": "left",
                }.get(arrow_key)
            if arrow_key in ("5", "6"):
                trailing_character = _read_key_if_available(file_descriptor, 0.15)
                if trailing_character != "~":
                    return None
                return "events_up" if arrow_key == "5" else "events_down"
            if arrow_key.isdigit():
                sequence_end = _read_key_if_available(file_descriptor, 0.15)
                if sequence_end != "~":
                    return None
                return None
            return {
                "A": "up",
                "B": "down",
                "C": "right",
                "D": "left",
            }.get(arrow_key)

        if pressed_key in ("\r", "\n"):
            return "select"

        if pressed_key.lower() == "q":
            return "quit"

        return pressed_key
    finally:
        termios.tcsetattr(file_descriptor, termios.TCSADRAIN, previous_settings)


def _read_key_if_available(file_descriptor: int, timeout_seconds: float) -> Optional[str]:
    ready_descriptors, _, _ = select.select([file_descriptor], [], [], timeout_seconds)
    if not ready_descriptors:
        return None
    return _read_key_from_descriptor(file_descriptor)


def _read_key_from_descriptor(file_descriptor: int) -> Optional[str]:
    key_bytes = os.read(file_descriptor, 1)
    if not key_bytes:
        return None
    return key_bytes.decode("utf-8", errors="ignore")


def _normalize_action_input(raw_command: str) -> Optional[str]:
    normalized_command = raw_command.strip().lower()
    if not normalized_command:
        return None

    if normalized_command in SUPPORTED_ACTIONS:
        return normalized_command

    if normalized_command in ("pageup", "pgup", "events-up", "events_up"):
        return "events_up"

    if normalized_command in ("pagedown", "pgdown", "events-down", "events_down"):
        return "events_down"

    if normalized_command in ("quit", "exit"):
        return normalized_command

    if normalized_command in ("new_pet", "new pet", "new"):
        return "new_pet"

    return None


def _snap_column_to_action(
    action_grid: Sequence[Sequence[Optional[str]]],
    row_index: int,
    preferred_column: int,
) -> int:
    row = action_grid[row_index]
    safe_column = max(0, min(preferred_column, len(row) - 1))
    if row[safe_column] is not None:
        return safe_column
    for column_index, cell in enumerate(row):
        if cell is not None:
            return column_index
    return 0


def _clamp_selection(
    action_grid: Sequence[Sequence[Optional[str]]],
    position: tuple[int, int],
) -> tuple[int, int]:
    if not action_grid:
        return (0, 0)
    row_index = max(0, min(position[0], len(action_grid) - 1))
    column_index = max(0, min(position[1], len(action_grid[row_index]) - 1))
    column_index = _snap_column_to_action(action_grid, row_index, column_index)
    return (row_index, column_index)


def _move_selection(
    action_grid: Sequence[Sequence[Optional[str]]],
    current_position: tuple[int, int],
    direction: str,
) -> tuple[int, int]:
    row_index, column_index = current_position

    if direction == "up":
        row_index = max(0, row_index - 1)
    elif direction == "down":
        row_index = min(len(action_grid) - 1, row_index + 1)
    elif direction == "left":
        column_index = max(0, column_index - 1)
    elif direction == "right":
        column_index = min(len(action_grid[row_index]) - 1, column_index + 1)

    column_index = _snap_column_to_action(action_grid, row_index, column_index)
    return (row_index, column_index)


def _command_from_grid_cell(cell: Optional[str]) -> str:
    if not cell:
        return ""
    if cell in ("lights_on", "lights_off"):
        return "lights"
    return cell


def _highlight_key_at_position(
    action_grid: Sequence[Sequence[Optional[str]]],
    position: tuple[int, int],
) -> str:
    return _command_from_grid_cell(_grid_value_at_position(action_grid, position))


def _grid_value_at_position(
    action_grid: Sequence[Sequence[Optional[str]]],
    position: tuple[int, int],
) -> Optional[str]:
    row_index, column_index = position
    return action_grid[row_index][column_index]


def _default_event_offset(pet_state: PetState, event_window_size: int) -> int:
    return max(0, len(pet_state.events) - event_window_size)


def _move_event_offset(
    pet_state: PetState,
    event_offset: int,
    event_window_size: int,
    step: int,
) -> int:
    max_offset = max(0, len(pet_state.events) - event_window_size)
    return max(0, min(max_offset, event_offset + step))
