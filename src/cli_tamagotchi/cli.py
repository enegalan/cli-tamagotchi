from __future__ import annotations

import argparse
import os
import select
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, TextIO

from rich.console import Console
from rich.live import Live
from rich.text import Text

from .engine import apply_action, create_new_pet, reconcile_state
from .models import PetState
from .render import render_interactive_view, render_status
from .storage import PetStorage

try:
    import termios
    import tty
except ImportError:  # pragma: no cover
    termios = None
    tty = None

SUPPORTED_ACTIONS = ("feed", "play", "lights", "clean")
EVENT_WINDOW_SIZE = 6
NO_ACTION = "__no_action__"
ACTION_GRID = (
    ("feed", "play"),
    ("lights", "clean"),
    ("status", "quit"),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tama", description="Care for your terminal pet.")
    parser.add_argument(
        "--name",
        default="Byte",
        help="Name for a new pet created on first launch.",
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("status", help="Show the current pet status.")
    subparsers.add_parser("feed", help="Feed your pet.")
    subparsers.add_parser("play", help="Play with your pet.")
    subparsers.add_parser("lights", help="Toggle the lights on or off.")
    subparsers.add_parser("clean", help="Clean your pet's space.")
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

    pet_state = load_or_create_pet(storage, now_provider(), args.name)

    if not args.command:
        return run_interactive_loop(
            pet_state=pet_state,
            storage=storage,
            now_provider=now_provider,
            console=console,
            output=output,
            input_stream=input_stream,
        )

    if args.command == "status":
        storage.save(pet_state)
        console.print(render_status(pet_state, compact=True))
        return 0

    result = apply_action(pet_state, args.command, now_provider())
    storage.save(result.pet_state)
    console.print(result.message, style="bold green")
    console.print(render_status(result.pet_state, compact=True))
    return 0


def load_or_create_pet(storage: PetStorage, now: datetime, pet_name: str) -> PetState:
    pet_state = storage.load()
    if pet_state is None:
        pet_state = create_new_pet(now=now, name=pet_name)
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
        )

    with Live(
        render_interactive_view(
            pet_state,
            _action_at_position(selected_position),
            event_offset=event_offset,
        ),
        console=console,
        screen=True,
        auto_refresh=False,
    ) as live:
        while True:
            live.update(
                render_interactive_view(
                    pet_state,
                    _action_at_position(selected_position),
                    event_offset=event_offset,
                    status_message=status_message,
                ),
                refresh=True,
            )

            raw_action = _read_action_input(output, input_stream)
            if raw_action is None:
                storage.save(pet_state)
                return 0
            if raw_action == NO_ACTION:
                continue

            if raw_action in ("up", "down", "left", "right"):
                selected_position = _move_selection(selected_position, raw_action)
                continue
            if raw_action == "events_up":
                event_offset = _move_event_offset(pet_state, event_offset, EVENT_WINDOW_SIZE, -1)
                continue
            if raw_action == "events_down":
                event_offset = _move_event_offset(pet_state, event_offset, EVENT_WINDOW_SIZE, 1)
                continue
            if raw_action == "select":
                command = _action_at_position(selected_position)
            else:
                command = _normalize_action_input(raw_action)
                if command is None:
                    status_message = Text("Unknown action.", style="bold red")
                    continue

            if command in ("quit", "exit"):
                storage.save(pet_state)
                live.update(
                    render_interactive_view(
                        pet_state,
                        _action_at_position(selected_position),
                        event_offset=event_offset,
                        status_message=Text("Goodbye.", style="bold cyan"),
                    ),
                    refresh=True,
                )
                return 0

            if command == "status":
                reconcile_state(pet_state, now_provider())
                storage.save(pet_state)
                event_offset = _default_event_offset(pet_state, EVENT_WINDOW_SIZE)
                status_message = None
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
) -> int:
    status_message: Optional[Text] = None
    selected_position = (0, 0)
    event_offset = _default_event_offset(pet_state, EVENT_WINDOW_SIZE)

    while True:
        console.print(
            render_interactive_view(
                pet_state,
                _action_at_position(selected_position),
                event_offset=event_offset,
                status_message=status_message,
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
            command = _action_at_position(selected_position)
        else:
            command = _normalize_action_input(raw_action)
            if command is None:
                status_message = Text("Unknown action.", style="bold red")
                continue

        if command in ("quit", "exit"):
            storage.save(pet_state)
            console.print("Goodbye.", style="bold cyan")
            return 0

        if command == "status":
            reconcile_state(pet_state, now_provider())
            storage.save(pet_state)
            event_offset = _default_event_offset(pet_state, EVENT_WINDOW_SIZE)
            status_message = None
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


def _read_action_input(output: TextIO, input_stream: TextIO) -> Optional[str]:
    if _supports_single_key_input(input_stream):
        single_key_action = _read_single_key(input_stream)
        if single_key_action is None:
            return NO_ACTION
        return single_key_action

    output.write("> ")
    output.flush()
    raw_command = input_stream.readline()
    if not raw_command:
        return None
    return raw_command


def _read_single_key(input_stream: TextIO) -> Optional[str]:
    file_descriptor = input_stream.fileno()
    previous_settings = termios.tcgetattr(file_descriptor)
    try:
        tty.setraw(file_descriptor)
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
        return "status"

    if normalized_command in SUPPORTED_ACTIONS:
        return normalized_command

    if normalized_command in ("pageup", "pgup", "events-up", "events_up"):
        return "events_up"

    if normalized_command in ("pagedown", "pgdown", "events-down", "events_down"):
        return "events_down"

    if normalized_command in ("status", "quit", "exit"):
        return normalized_command

    return None


def _move_selection(current_position: tuple[int, int], direction: str) -> tuple[int, int]:
    row_index, column_index = current_position

    if direction == "up":
        row_index = max(0, row_index - 1)
    elif direction == "down":
        row_index = min(len(ACTION_GRID) - 1, row_index + 1)
    elif direction == "left":
        column_index = max(0, column_index - 1)
    elif direction == "right":
        column_index = min(len(ACTION_GRID[row_index]) - 1, column_index + 1)

    if _grid_value_at_position((row_index, column_index)) is None:
        column_index = 0

    return (row_index, column_index)


def _action_at_position(position: tuple[int, int]) -> str:
    selected_action = _grid_value_at_position(position)
    if selected_action is None:
        return "quit"
    return selected_action


def _grid_value_at_position(position: tuple[int, int]) -> Optional[str]:
    row_index, column_index = position
    return ACTION_GRID[row_index][column_index]


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
