from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import re
import select
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, Sequence, TextIO

from rich.console import Console, Group
from rich.live import Live
from rich.table import Table
from rich.text import Text

from .characters import character_status_label
from .engine import apply_action, create_new_pet, pick_random_pet_name, reconcile_state
from .models import PetState
from .graveyard import GraveyardEntry
from .render import (
    GRAVEYARD_PAGE_SIZE,
    NAME_HATCH_MAX_CHARS,
    _lights_action_name,
    render_event_log,
    render_graveyard_status_compact,
    render_graveyard_view,
    render_interactive_view,
    render_name_hatch_view,
    render_share_card_plain,
    render_status,
)
from .plugins.manager import DISTRIBUTION_PIP_SPEC, list_plugin_entry_point_specs, plugin_manager
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
            ("medicine", "graveyard"),
            ("quit", None),
        )
    if storage.can_create_new_pet(pet_state):
        return (
            ("new_pet", "graveyard"),
            ("quit", None),
        )
    return (("graveyard", "quit"),)


def _package_version_string() -> str:
    try:
        return importlib.metadata.version("cli-tamagotchi")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0-dev"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tama", description="Care for your terminal pet.")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_package_version_string()}",
    )
    subparsers = parser.add_subparsers(dest="command")
    status_parser = subparsers.add_parser("status", help="Show pet status (current, by name, or pick from list).")
    status_parser.add_argument(
        "--name",
        dest="status_name",
        nargs="?",
        const="",
        default=None,
        metavar="PET",
        help="Pet name (alive or graveyard). Use --name with no value to choose from a list.",
    )
    status_parser.add_argument(
        "--json",
        dest="status_json",
        action="store_true",
        help="Print status as JSON (pet or graveyard entry) instead of the TUI-style view.",
    )
    subparsers.add_parser("feed", help="Feed your pet.")
    subparsers.add_parser("play", help="Play with your pet.")
    subparsers.add_parser("lights", help="Toggle the lights on or off.")
    subparsers.add_parser("clean", help="Clean your pet's space.")
    subparsers.add_parser("medicine", help="Give medicine (cooldown 1h, cures illness, restores health).")
    subparsers.add_parser("new", help="Start a new pet (only if none is alive).")
    subparsers.add_parser("logs", help="Show the pet event log.")
    subparsers.add_parser("graveyard", help="List pets that have passed away.")
    share_parser = subparsers.add_parser(
        "share",
        help="Print a shareable plain-text pet card (sprite + stats).",
    )
    share_parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy the card to the clipboard (pbcopy, wl-copy, xclip, or clip).",
    )
    share_parser.add_argument(
        "--save",
        action="store_true",
        help="Write <name>_card.txt in the current directory.",
    )
    share_parser.add_argument(
        "--name",
        dest="share_name",
        default=None,
        metavar="PET",
        help="Share a specific pet by name (current pet or graveyard).",
    )
    plugin_parser = subparsers.add_parser("plugin", help="Plugin commands.")
    plugin_sub = plugin_parser.add_subparsers(dest="plugin_command", required=True)
    plugin_sub.add_parser("list", help="List plugins loaded in this process.")
    plugin_sub.add_parser(
        "available",
        help="List cli_tamagotchi.plugins entry points visible in this Python environment.",
    )
    install_parser = plugin_sub.add_parser(
        "install",
        help="Pick a plugin to install or pass index / entry name (see `tama plugin available`).",
    )
    install_parser.add_argument(
        "choice",
        nargs="?",
        default=None,
        metavar="N|NAME",
        help="Optional: 1-based index from the menu or setuptools entry name (e.g. claude_code).",
    )
    emit_parser = plugin_sub.add_parser(
        "emit",
        help="Invoke on_external_event on plugins (all, or one with --plugin).",
    )
    emit_parser.add_argument(
        "--plugin",
        "-p",
        dest="plugin_target",
        default=None,
        metavar="NAME",
        help="Only notify plugins matching this logical name or setuptools entry name.",
    )
    emit_parser.add_argument("event_type", help="Opaque event type string.")
    emit_parser.add_argument(
        "--data",
        default="{}",
        help="JSON object passed to plugins (default: {}).",
    )
    return parser


def _clipboard_command() -> Optional[list[str]]:
    if sys.platform == "darwin" and shutil.which("pbcopy"):
        return ["pbcopy"]
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        return ["wl-copy"]
    if shutil.which("xclip"):
        return ["xclip", "-selection", "clipboard"]
    if sys.platform == "win32" and shutil.which("clip"):
        return ["clip"]
    return None


def _copy_card_to_clipboard(text: str) -> None:
    cmd = _clipboard_command()
    if cmd is None:
        raise RuntimeError(
            "No clipboard utility found. On macOS use pbcopy; on Linux Wayland use wl-copy; "
            "on X11 install xclip; on Windows use clip."
        )
    if sys.platform == "win32":
        subprocess.run(cmd, input=text, text=True, encoding="utf-8", check=True)
    else:
        subprocess.run(cmd, input=text.encode("utf-8"), check=True)


def _safe_share_card_filename(pet_name: str) -> str:
    base = pet_name.strip() or "pet"
    safe = re.sub(r"[^\w\-. ]+", "_", base, flags=re.UNICODE)
    safe = re.sub(r"_+", "_", safe)
    safe = safe.replace(" ", "_").strip("._") or "pet"
    return f"{safe}_card.txt"


def _resolve_share_subject(
    pet_state: Optional[PetState],
    graveyard: list[GraveyardEntry],
    name: Optional[str],
) -> tuple[Optional[PetState | GraveyardEntry], Optional[str]]:
    if not name or not name.strip():
        if pet_state is None:
            return None, "No pet found. Hatch one first."
        return pet_state, None
    needle = name.strip().lower()
    if pet_state is not None and pet_state.name.strip().lower() == needle:
        return pet_state, None
    matches = [entry for entry in graveyard if entry.name.strip().lower() == needle]
    if not matches:
        return None, f"No pet named {name.strip()!r} in your save or graveyard."
    best = max(matches, key=lambda entry: entry.died_at)
    return best, None


def _share_card_display_name(subject: PetState | GraveyardEntry) -> str:
    if isinstance(subject, GraveyardEntry):
        return subject.name
    return subject.name


def _status_subject_json_object(subject: PetState | GraveyardEntry) -> dict[str, Any]:
    if isinstance(subject, PetState):
        return {
            "kind": "pet",
            "pet": subject.to_dict(),
            "mood": subject.mood(),
            "stage_age_hours": subject.stage_age_hours(),
            "character_label": character_status_label(subject.character),
        }
    return {
        "kind": "graveyard",
        "entry": subject.to_dict(),
        "character_label": character_status_label(subject.character),
    }


def _emit_status_view(
    subject: PetState | GraveyardEntry,
    *,
    as_json: bool,
    output: TextIO,
    console: Console,
    now: datetime,
) -> None:
    if as_json:
        payload = _status_subject_json_object(subject)
        output.write(json.dumps(payload, indent=2) + "\n")
        output.flush()
        return
    if isinstance(subject, PetState):
        console.print(render_status(subject, compact=True, animation_time=now))
    else:
        console.print(render_graveyard_status_compact(subject, animation_time=now))


def _graveyard_entries_for_status_selector(
    pet_state: Optional[PetState],
    graveyard: list[GraveyardEntry],
) -> list[GraveyardEntry]:
    if pet_state is None or pet_state.is_alive:
        return list(graveyard)
    result: list[GraveyardEntry] = []
    skipped_duplicate = False
    for entry in graveyard:
        if (
            not skipped_duplicate
            and entry.name.strip().lower() == pet_state.name.strip().lower()
            and entry.died_at == pet_state.stage_started_at
        ):
            skipped_duplicate = True
            continue
        result.append(entry)
    return result


def _build_status_selector_rows(
    pet_state: Optional[PetState],
    graveyard: list[GraveyardEntry],
) -> list[tuple[str, PetState | GraveyardEntry]]:
    rows: list[tuple[str, PetState | GraveyardEntry]] = []
    if pet_state is not None:
        if pet_state.is_alive:
            rows.append((f"{pet_state.name} · alive", pet_state))
        else:
            rows.append((f"{pet_state.name} · current save (passed)", pet_state))
    filtered = _graveyard_entries_for_status_selector(pet_state, graveyard)
    for entry in sorted(filtered, key=lambda e: e.died_at, reverse=True):
        rows.append((f"{entry.name} · died {entry.died_at.strftime('%Y-%m-%d %H:%M')}", entry))
    return rows


def _prompt_status_pet_selector(
    pet_state: Optional[PetState],
    graveyard: list[GraveyardEntry],
    console: Console,
    input_stream: TextIO,
) -> Optional[PetState | GraveyardEntry]:
    menu_rows = _build_status_selector_rows(pet_state, graveyard)
    if not menu_rows:
        console.print("No pets in save or graveyard.", style="bold red")
        return None
    if not input_stream.isatty():
        console.print("No TTY: pass a pet name, e.g. `tama status --name Nova`.", style="bold red")
        console.print("Options:")
        for i, (label, _) in enumerate(menu_rows, start=1):
            console.print(f"  {i}) {label}")
        return None
    console.print("Choose a pet:")
    for i, (label, _) in enumerate(menu_rows, start=1):
        console.print(f"  {i}) {label}")
    try:
        line = input_stream.readline()
    except Exception:
        return None
    if not line:
        console.print("No selection.", style="bold red")
        return None
    needle = line.strip()
    if not needle.isdigit():
        console.print(
            f"Invalid choice {needle!r}; enter a number from 1 to {len(menu_rows)}.",
            style="bold red",
        )
        return None
    idx = int(needle)
    if not (1 <= idx <= len(menu_rows)):
        console.print(f"Invalid index {idx}; use 1–{len(menu_rows)}.", style="bold red")
        return None
    return menu_rows[idx - 1][1]


def _init_plugins(storage: PetStorage) -> None:
    plugin_manager.configure(storage.base_dir)
    plugin_manager.discover(user_plugin_dir=storage.base_dir / "plugins")


def _pip_spec_for_entry_point(ep: importlib.metadata.EntryPoint) -> str:
    dist = getattr(ep, "dist", None)
    if dist is not None:
        try:
            return dist.metadata["Name"]
        except Exception:
            pass
    return DISTRIBUTION_PIP_SPEC


def _plugin_install_menu_rows(
    eps: list[importlib.metadata.EntryPoint],
) -> list[tuple[str, str, str]]:
    """(menu label, pip_spec, match_key) — match_key is entry name or package for CLI matching."""
    rows: list[tuple[str, str, str]] = []
    if not eps:
        rows.append(
            (
                f"{DISTRIBUTION_PIP_SPEC} (application package; registers plugins from this project)",
                DISTRIBUTION_PIP_SPEC,
                DISTRIBUTION_PIP_SPEC,
            )
        )
        return rows
    for ep in eps:
        pip_spec = _pip_spec_for_entry_point(ep)
        target = getattr(ep, "value", None) or f"{ep.module}:{ep.attr}"
        label = f"{ep.name} — package: {pip_spec} — {target}"
        rows.append((label, pip_spec, ep.name))
    return rows


def _resolve_plugin_install_choice(
    choice: str,
    menu_rows: list[tuple[str, str, str]],
    console: Console,
) -> tuple[str, str] | None:
    """Return (pip_spec, summary_key) or None. summary_key is entry name or package id for messages."""
    needle = choice.strip()
    if not needle:
        return None
    n = len(menu_rows)
    if needle.isdigit():
        idx = int(needle)
        if 1 <= idx <= n:
            _label, pip_spec, key = menu_rows[idx - 1]
            return pip_spec, key
        console.print(f"Invalid index {idx}; use 1–{n}.", style="bold red")
        return None
    low = needle.lower()
    for _label, pip_spec, entry_name in menu_rows:
        if entry_name.lower() == low or pip_spec.lower() == low:
            return pip_spec, entry_name
    console.print(f"Unknown choice {needle!r}. Use a number or entry name from the list.", style="bold red")
    return None


def _prompt_plugin_install_pip_spec(
    args_choice: str | None,
    console: Console,
    input_stream: TextIO,
) -> tuple[str, str] | None:
    """Return (pip_spec, summary_key) or None."""
    eps = list_plugin_entry_point_specs()
    menu_rows = _plugin_install_menu_rows(eps)
    if args_choice is not None and args_choice.strip() != "":
        return _resolve_plugin_install_choice(args_choice, menu_rows, console)

    if not input_stream.isatty():
        console.print(
            "No TTY: pass a choice, e.g. `tama plugin install 1` or `tama plugin install claude_code`.",
            style="bold red",
        )
        console.print("Options:")
        for i, (label, _pip, _mk) in enumerate(menu_rows, start=1):
            console.print(f"  {i}) {label}")
        return None

    console.print("Which plugin do you want to install? (pip installs the package that provides it)")
    for i, (label, _pip, _mk) in enumerate(menu_rows, start=1):
        console.print(f"  {i}) {label}")
    try:
        line = input_stream.readline()
    except Exception:
        return None
    if not line:
        return None
    return _resolve_plugin_install_choice(line, menu_rows, console)


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
    _init_plugins(storage)

    pet_state = storage.load()
    if pet_state is not None:
        reconcile_state(pet_state, now_provider())
        storage.save(pet_state)

    if args.command == "graveyard":
        console.print(render_graveyard_view(storage.load_graveyard()))
        return 0

    if args.command == "share":
        graveyard_entries = storage.load_graveyard()
        subject, err = _resolve_share_subject(pet_state, graveyard_entries, getattr(args, "share_name", None))
        if err is not None:
            console.print(err, style="bold red")
            return 1
        assert subject is not None
        card_text = render_share_card_plain(subject, animation_time=now_provider())
        emit_stdout = not args.copy and not args.save
        if emit_stdout:
            output.write(card_text)
            if not card_text.endswith("\n"):
                output.write("\n")
            output.flush()
        if args.copy:
            try:
                _copy_card_to_clipboard(card_text)
            except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
                console.print(f"Could not copy to clipboard: {exc}", style="bold red")
                return 1
            if emit_stdout:
                console.print("Also copied pet card to clipboard.", style="dim")
            else:
                console.print("Copied pet card to clipboard.", style="bold green")
        if args.save:
            filename = _safe_share_card_filename(_share_card_display_name(subject))
            path = Path.cwd() / filename
            try:
                path.write_text(card_text + ("\n" if not card_text.endswith("\n") else ""), encoding="utf-8")
            except OSError as exc:
                console.print(f"Could not save card: {exc}", style="bold red")
                return 1
            if not emit_stdout:
                console.print(f"Wrote pet card to {path}.", style="bold green")
            else:
                console.print(f"Also saved pet card to {path}.", style="dim")
        return 0

    if args.command == "plugin":
        if args.plugin_command == "list":
            if not plugin_manager.plugins:
                console.print("No plugins loaded.")
                return 0
            table = Table(show_header=True, header_style="bold")
            table.add_column("Name")
            table.add_column("Version")
            table.add_column("Source")
            table.add_column("Description")
            for plugin in plugin_manager.plugins:
                meta = plugin_manager.meta_for(plugin)
                if meta and meta.kind == "entry_point":
                    source_cell = f"entry:{meta.entry_name}"
                    if meta.distribution:
                        source_cell = f"{source_cell} ({meta.distribution})"
                elif meta and meta.kind == "user_file" and meta.path:
                    source_cell = f"file:{meta.path}"
                elif meta and meta.kind == "manual":
                    source_cell = "manual"
                else:
                    source_cell = "?"
                table.add_row(plugin.name, plugin.version, source_cell, plugin.description)
            console.print(table)
            return 0

        if args.plugin_command == "available":
            loaded_entry_names: set[str] = set()
            for plugin in plugin_manager.plugins:
                meta = plugin_manager.meta_for(plugin)
                if meta and meta.entry_name:
                    loaded_entry_names.add(meta.entry_name)
            eps = list_plugin_entry_point_specs()
            if not eps:
                console.print(
                    "No cli_tamagotchi.plugins entry points in this environment. "
                    f"Install: `tama plugin install` or `pip install {DISTRIBUTION_PIP_SPEC}`.",
                )
                return 0
            table = Table(
                title="cli_tamagotchi.plugins",
                show_header=True,
                header_style="bold",
            )
            table.add_column("Name")
            table.add_column("Target")
            table.add_column("Distribution")
            table.add_column("Loaded")
            for ep in eps:
                dist = getattr(ep, "dist", None)
                dist_name = ""
                if dist is not None:
                    try:
                        dist_name = dist.metadata["Name"]
                    except Exception:
                        dist_name = ""
                target_cell = getattr(ep, "value", None) or f"{ep.module}:{ep.attr}"
                table.add_row(
                    ep.name,
                    target_cell,
                    dist_name or "—",
                    "yes" if ep.name in loaded_entry_names else "no",
                )
            console.print(table)
            return 0

        if args.plugin_command == "install":
            picked = _prompt_plugin_install_pip_spec(getattr(args, "choice", None), console, input_stream)
            if picked is None:
                return 1
            pip_spec, summary_key = picked
            try:
                completed = subprocess.run(
                    [sys.executable, "-m", "pip", "install", pip_spec],
                    capture_output=True,
                    text=True,
                )
            except OSError as exc:
                console.print(f"Could not run pip: {exc}", style="bold red")
                return 1
            if completed.stdout:
                console.print(completed.stdout.rstrip())
            if completed.stderr:
                console.print(completed.stderr.rstrip())
            if completed.returncode != 0:
                console.print("pip install failed.", style="bold red")
                return completed.returncode
            console.print(
                f"Installed package {pip_spec} (choice: {summary_key}). Restart `tama` to load plugins.",
                style="bold green",
            )
            return 0

        if args.plugin_command == "emit":
            if pet_state is None:
                console.print("No pet found. Hatch one in the TUI first.", style="bold red")
                return 1
            try:
                data_payload = json.loads(args.data)
            except json.JSONDecodeError:
                console.print("Invalid JSON for --data.", style="bold red")
                return 1
            if not isinstance(data_payload, dict):
                console.print("--data must be a JSON object.", style="bold red")
                return 1
            if args.plugin_target and not plugin_manager.plugins_matching(args.plugin_target):
                console.print(
                    f"No plugin matches {args.plugin_target!r}. Try `tama plugin list`.",
                    style="bold red",
                )
                return 1
            reconcile_state(pet_state, now_provider())
            plugin_manager.emit(
                "on_external_event",
                target=args.plugin_target,
                event_type=args.event_type,
                data=data_payload,
            )
            storage.save(pet_state)
            label = args.event_type
            if args.plugin_target:
                label = f"{label} -> {args.plugin_target}"
            console.print(f"Emitted plugin event: {label}", style="bold green")
        return 0

    if not args.command:
        return run_interactive_loop(
            pet_state=pet_state,
            storage=storage,
            now_provider=now_provider,
            console=console,
            output=output,
            input_stream=input_stream,
        )

    if args.command == "new":
        if pet_state is not None and pet_state.is_alive:
            console.print("A pet is already alive. You can only have one living pet.", style="bold red")
            return 1
        if pet_state is not None:
            storage.save_dead_before_hatching_replacement(pet_state)
        new_name = prompt_pet_name_on_hatch(output, input_stream)
        pet_state = create_new_pet(now=now_provider(), name=new_name)
        storage.save(pet_state)
        console.print(f"A new pet, {pet_state.name}, has hatched.", style="bold green")
        console.print(render_status(pet_state, compact=True, animation_time=now_provider()))
        return 0

    status_name_arg = getattr(args, "status_name", None) if args.command == "status" else None
    status_as_json = bool(getattr(args, "status_json", False))
    if status_name_arg is not None:
        graveyard = storage.load_graveyard()
        if status_name_arg == "":
            chosen = _prompt_status_pet_selector(pet_state, graveyard, console, input_stream)
            if chosen is None:
                return 1
            if isinstance(chosen, PetState):
                reconcile_state(chosen, now_provider())
                storage.save(chosen)
            now = now_provider()
            _emit_status_view(
                chosen,
                as_json=status_as_json,
                output=output,
                console=console,
                now=now,
            )
            return 0
        name_trimmed = status_name_arg.strip()
        if not name_trimmed:
            console.print("Use `tama status --name` alone for the pet picker, or pass a non-empty name.", style="bold red")
            return 1
        subject, resolve_error = _resolve_share_subject(pet_state, graveyard, name_trimmed)
        if resolve_error:
            console.print(resolve_error, style="bold red")
            return 1
        assert subject is not None
        if isinstance(subject, PetState):
            reconcile_state(subject, now_provider())
            storage.save(subject)
        now = now_provider()
        _emit_status_view(
            subject,
            as_json=status_as_json,
            output=output,
            console=console,
            now=now,
        )
        return 0

    if pet_state is None:
        bootstrap_name = prompt_pet_name_on_hatch(output, input_stream)
        pet_state = create_new_pet(now=now_provider(), name=bootstrap_name)
        storage.save(pet_state)

    if args.command == "status":
        storage.save(pet_state)
        now = now_provider()
        _emit_status_view(
            pet_state,
            as_json=status_as_json,
            output=output,
            console=console,
            now=now,
        )
        return 0

    if args.command == "logs":
        storage.save(pet_state)
        console.print(render_event_log(pet_state))
        return 0

    result = apply_action(pet_state, args.command, now_provider())
    storage.save(result.pet_state)
    console.print(result.message, style="bold green")
    console.print(render_status(result.pet_state, compact=True, animation_time=now_provider()))
    return 0


def prompt_pet_name_on_hatch(
    output: TextIO,
    input_stream: TextIO,
    *,
    prompt_prefix: Optional[str] = None,
) -> str:
    return _prompt_pet_name_line(output, input_stream, prompt_prefix=prompt_prefix)


def _prompt_pet_name_in_tui(
    live: Live,
    input_stream: TextIO,
    output: TextIO,
    *,
    backdrop_pet: Optional[PetState],
    now_provider: Callable[[], datetime],
) -> Optional[str]:
    if not _supports_single_key_input(input_stream):
        return _prompt_pet_name_line(output, input_stream, prompt_prefix="\n> ")

    event_offset = (
        _default_event_offset(backdrop_pet, EVENT_WINDOW_SIZE) if backdrop_pet is not None else 0
    )
    name_buffer = ""
    while True:
        current_time = now_provider()
        live.update(
            Group(
                render_name_hatch_view(
                    name_buffer,
                    backdrop_pet,
                    event_offset,
                    current_time,
                )
            ),
            refresh=True,
        )
        key = _read_single_key(input_stream, idle_timeout_seconds=None, for_name_prompt=True)
        if key is None:
            continue
        if key == "name_cancel":
            return None
        if key == "select":
            stripped = name_buffer.strip()
            return stripped if stripped else pick_random_pet_name()
        if key == "name_backspace":
            name_buffer = name_buffer[:-1]
            continue
        if key and len(key) == 1 and key.isprintable():
            if len(name_buffer) < NAME_HATCH_MAX_CHARS:
                name_buffer += key
            continue


def _prompt_pet_name_line(
    output: TextIO,
    input_stream: TextIO,
    *,
    prompt_prefix: Optional[str] = None,
) -> str:
    input_is_tty = bool(getattr(input_stream, "isatty", lambda: False)())
    if not input_is_tty:
        return pick_random_pet_name()
    line_prefix = (
        "\nPet name (Enter for random): " if prompt_prefix is None else prompt_prefix
    )
    output.write(line_prefix)
    output.flush()
    line = input_stream.readline()
    if not line:
        return pick_random_pet_name()
    stripped_line = line.strip()
    return stripped_line if stripped_line else pick_random_pet_name()


def run_interactive_loop(
    pet_state: Optional[PetState],
    storage: PetStorage,
    now_provider: Callable[[], datetime],
    console: Console,
    output: TextIO,
    input_stream: TextIO,
) -> int:
    status_message: Optional[Text] = None
    selected_position = (0, 0)
    screen_mode = "pet"
    graveyard_scroll = 0
    if not _supports_fullscreen(output, input_stream):
        return _run_interactive_loop_fallback(
            pet_state=pet_state,
            storage=storage,
            now_provider=now_provider,
            console=console,
            output=output,
            input_stream=input_stream,
        )

    working_pet: Optional[PetState] = pet_state
    now_initial = now_provider()
    if working_pet is None:
        live_initial = Group(render_name_hatch_view("", None, 0, now_initial))
    else:
        initial_grid = build_action_grid(working_pet, storage)
        selected_position = _clamp_selection(initial_grid, selected_position)
        live_initial = render_interactive_view(
            working_pet,
            _highlight_key_at_position(initial_grid, selected_position),
            event_offset=_default_event_offset(working_pet, EVENT_WINDOW_SIZE),
            status_message=status_message,
            animation_time=now_initial,
            action_rows=initial_grid,
        )

    with Live(
        live_initial,
        console=console,
        screen=True,
        auto_refresh=False,
    ) as live:
        if working_pet is None:
            hatch_name = _prompt_pet_name_in_tui(
                live,
                input_stream,
                output,
                backdrop_pet=None,
                now_provider=now_provider,
            )
            if hatch_name is None:
                return 0
            working_pet = create_new_pet(now_provider(), hatch_name)
            storage.save(working_pet)
            status_message = Text(
                f"{working_pet.name} hatched! Welcome to cli-tamagotchi.",
                style="bold green",
            )

        assert working_pet is not None
        pet_state = working_pet
        event_offset = _default_event_offset(pet_state, EVENT_WINDOW_SIZE)
        action_grid = build_action_grid(pet_state, storage)
        selected_position = _clamp_selection(action_grid, (0, 0))

        while True:
            current_time = now_provider()
            reconcile_state(pet_state, current_time)
            action_grid = build_action_grid(pet_state, storage)
            selected_position = _clamp_selection(action_grid, selected_position)

            if screen_mode == "graveyard":
                entries = storage.load_graveyard()
                max_grave_scroll = max(0, len(entries) - GRAVEYARD_PAGE_SIZE)
                graveyard_scroll = max(0, min(graveyard_scroll, max_grave_scroll))
                live.update(Group(render_graveyard_view(entries, graveyard_scroll)), refresh=True)
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
                if raw_action in ("up", "down"):
                    if raw_action == "up":
                        graveyard_scroll = max(0, graveyard_scroll - 1)
                    else:
                        graveyard_scroll = min(max_grave_scroll, graveyard_scroll + 1)
                    continue
                if raw_action in ("quit", "select"):
                    screen_mode = "pet"
                    status_message = None
                    continue
                continue

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

            if command == "graveyard":
                entries = storage.load_graveyard()
                graveyard_scroll = max(0, len(entries) - GRAVEYARD_PAGE_SIZE)
                screen_mode = "graveyard"
                continue

            if command == "new_pet":
                if pet_state.is_alive:
                    status_message = Text("You already have a living pet.", style="bold red")
                    continue
                if not storage.can_create_new_pet(pet_state):
                    status_message = Text("Cannot start a new pet right now.", style="bold red")
                    continue
                hatch_name = _prompt_pet_name_in_tui(
                    live,
                    input_stream,
                    output,
                    backdrop_pet=pet_state,
                    now_provider=now_provider,
                )
                if hatch_name is None:
                    status_message = Text("Hatching cancelled.", style="yellow")
                    continue
                storage.save_dead_before_hatching_replacement(pet_state)
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
    pet_state: Optional[PetState],
    storage: PetStorage,
    now_provider: Callable[[], datetime],
    console: Console,
    output: TextIO,
    input_stream: TextIO,
) -> int:
    status_message: Optional[Text] = None
    selected_position = (0, 0)
    screen_mode = "pet"
    graveyard_scroll = 0
    if pet_state is None:
        console.print(render_name_hatch_view("", None, 0, now_provider()))
        bootstrap_name = _prompt_pet_name_line(output, input_stream, prompt_prefix="\n> ")
        pet_state = create_new_pet(now_provider(), bootstrap_name)
        storage.save(pet_state)
        status_message = Text(
            f"{pet_state.name} hatched! Welcome to cli-tamagotchi.",
            style="bold green",
        )

    assert pet_state is not None
    event_offset = _default_event_offset(pet_state, EVENT_WINDOW_SIZE)

    while True:
        reconcile_state(pet_state, now_provider())
        action_grid = build_action_grid(pet_state, storage)
        selected_position = _clamp_selection(action_grid, selected_position)

        if screen_mode == "graveyard":
            entries = storage.load_graveyard()
            max_grave_scroll = max(0, len(entries) - GRAVEYARD_PAGE_SIZE)
            graveyard_scroll = max(0, min(graveyard_scroll, max_grave_scroll))
            console.print(render_graveyard_view(entries, graveyard_scroll))
            raw_action = _read_action_input(output, input_stream)
            if raw_action is None:
                storage.save(pet_state)
                return 0
            if raw_action == NO_ACTION:
                continue
            normalized = _normalize_action_input(raw_action) if isinstance(raw_action, str) else None
            if raw_action in ("up", "down"):
                if raw_action == "up":
                    graveyard_scroll = max(0, graveyard_scroll - 1)
                else:
                    graveyard_scroll = min(max_grave_scroll, graveyard_scroll + 1)
                continue
            if raw_action in ("quit", "select"):
                screen_mode = "pet"
                status_message = None
                continue
            if isinstance(raw_action, str):
                line_lower = raw_action.strip().lower()
                if line_lower in ("q", "quit", "back") or _normalize_action_input(raw_action) == "quit":
                    screen_mode = "pet"
                    status_message = None
                    continue
            continue

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

        if command == "graveyard":
            entries = storage.load_graveyard()
            graveyard_scroll = max(0, len(entries) - GRAVEYARD_PAGE_SIZE)
            screen_mode = "graveyard"
            continue

        if command == "new_pet":
            if pet_state.is_alive:
                status_message = Text("You already have a living pet.", style="bold red")
                continue
            if not storage.can_create_new_pet(pet_state):
                status_message = Text("Cannot start a new pet right now.", style="bold red")
                continue
            hatch_name = prompt_pet_name_on_hatch(output, input_stream)
            storage.save_dead_before_hatching_replacement(pet_state)
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
    *,
    for_name_prompt: bool = False,
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

        if for_name_prompt:
            if pressed_key == "\x03":
                raise KeyboardInterrupt
            if pressed_key == "\x04":
                return "select"
            if pressed_key in ("\x7f", "\x08"):
                return "name_backspace"
        elif pressed_key in ("\x03", "\x04"):
            return "quit"

        if pressed_key == "\x1b":
            next_character = _read_key_if_available(file_descriptor, 0.15)
            if not next_character:
                return "name_cancel" if for_name_prompt else None
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

        if pressed_key.lower() == "q" and not for_name_prompt:
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

    if normalized_command in ("graveyard", "cemetery"):
        return "graveyard"


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
