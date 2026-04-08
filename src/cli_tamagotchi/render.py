from __future__ import annotations

from datetime import datetime

from rich.align import Align
from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .characters import character_status_label
from .engine import TICK_MINUTES
from .illnesses import ILLNESS_DEFINITION_BY_ENUM, illness_from_value
from .models import CHARACTER_STYLE_BY_NAME, STAGE_STYLE_BY_NAME, PetState
from .sprites import get_sprite_lines

STAT_BAR_FILL_HIGH = {
    "hunger": "bright_yellow",
    "happiness": "bright_magenta",
    "health": "bright_green",
    "energy": "bright_cyan",
}
STAT_BAR_FILL_MID = {
    "hunger": "yellow",
    "happiness": "magenta",
    "health": "green",
    "energy": "cyan",
}
ACTION_EMOJI = {
    "feed": "🍔",
    "play": "🎾",
    "lights_off": "🌙",
    "lights_on": "💡",
    "clean": "🧼",
    "medicine": "💊",
    "quit": "🚪",
    "new_pet": "🥚",
}
EVENT_EMOJI = {
    "hatched": "🥚",
    "grew into": "✨",
    "fed": "🍔",
    "played": "🎾",
    "lights off": "🌙",
    "lights on": "💡",
    "clean": "🧼",
}


def _illness_summary_columns(pet_state: PetState) -> tuple[str, str]:
    if not pet_state.active_illnesses:
        return "None", ""
    illness_parts: list[str] = list()
    tick_hints: list[str] = list()
    for entry in pet_state.active_illnesses:
        ill = illness_from_value(entry.illness_id)
        if ill is None:
            continue
        illness_parts.append(ILLNESS_DEFINITION_BY_ENUM[ill].display_name)
        if entry.ticks_remaining is not None:
            tick_hints.append(f"~{entry.ticks_remaining * TICK_MINUTES}m")
    illness_display = ", ".join(illness_parts) if illness_parts else "None"
    if not tick_hints:
        return illness_display, ""
    return illness_display, ", ".join(tick_hints)


def render_status(
    pet_state: PetState,
    compact: bool = False,
    event_offset: int = 0,
    event_limit: int = 6,
    animation_time: datetime | None = None,
):
    mood = pet_state.mood()
    reaction_pose = pet_state.reaction_pose_id(animation_time)
    raw_sprite_lines = get_sprite_lines(
        pet_state.character,
        pet_state.stage,
        mood,
        pet_state.is_asleep,
        reaction_pose=reaction_pose,
        animation_time=animation_time,
    )
    sprite_indent = min(len(line) - len(line.lstrip(" ")) for line in raw_sprite_lines if line.strip())
    sprite_lines = [line[sprite_indent:] for line in raw_sprite_lines]
    sprite_width = max(len(line) for line in sprite_lines)
    stats_row_count = 10
    status_panel_height = max(len(sprite_lines), stats_row_count) + 2
    sprite_inner_height = status_panel_height - 2
    sprite_vertical_gap = max(0, sprite_inner_height - len(sprite_lines))
    sprite_top_padding = sprite_vertical_gap // 2
    sprite_bottom_padding = sprite_vertical_gap - sprite_top_padding
    centered_sprite_lines = ([""] * sprite_top_padding) + sprite_lines + ([""] * sprite_bottom_padding)

    sprite_panel = Panel(
        Align.center(
            Text("\n".join(centered_sprite_lines)),
        ),
        title=Text(pet_state.name, style="magenta"),
        border_style=_mood_style(mood),
        height=status_panel_height,
        box=box.ROUNDED,
        padding=(0, 1),
    )

    stats_table = Table.grid(expand=True, padding=(0, 1))
    stats_table.add_column(justify="left", no_wrap=True)
    stats_table.add_column(justify="left", ratio=1)
    stats_table.add_column(justify="right", no_wrap=True)
    stats_table.add_row(
        Text("Character", style="bold"),
        Text(
            character_status_label(pet_state.character),
            style=CHARACTER_STYLE_BY_NAME.get(pet_state.character, "white"),
        ),
        Text(""),
    )
    stats_table.add_row(
        Text("Stage", style="bold"),
        Text(f"{pet_state.stage}", style=STAGE_STYLE_BY_NAME.get(pet_state.stage, "white")),
        Text(f"Age {pet_state.stage_age_hours()}h", style="dim"),
    )
    stats_table.add_row(
        Text("Weight", style="bold"),
        Text(str(pet_state.weight), style="white"),
        Text(""),
    )
    stats_table.add_row(
        Text("State", style="bold"),
        Text("Asleep", style="magenta") if pet_state.is_asleep else Text("Awake", style="green"),
        Text("🌙" if pet_state.is_asleep else "☀️"),
    )
    stats_table.add_row(
        Text("Dirtiness", style="bold"),
        Text(f"{pet_state.dirtiness}/3", style="white"),
        Text(""),
    )
    illness_display, illness_hint = _illness_summary_columns(pet_state)
    illness_style = "yellow" if pet_state.active_illnesses else "dim"
    stats_table.add_row(
        Text("Illness", style="bold"),
        Text(illness_display, style=illness_style),
        Text(illness_hint, style="dim"),
    )
    stats_table.add_row(
        Text("Hunger", style="bold"),
        stat_bar("hunger", pet_state.hunger),
        stat_value("hunger", pet_state.hunger),
    )
    stats_table.add_row(
        Text("Happiness", style="bold"),
        stat_bar("happiness", pet_state.happiness),
        stat_value("happiness", pet_state.happiness),
    )
    stats_table.add_row(
        Text("Health", style="bold"),
        stat_bar("health", pet_state.health),
        stat_value("health", pet_state.health),
    )
    stats_table.add_row(
        Text("Energy", style="bold"),
        stat_bar("energy", pet_state.energy),
        stat_value("energy", pet_state.energy),
    )

    stats_panel = Panel(
        Align.left(stats_table, vertical="middle"),
        title="Stats",
        border_style="dim",
        height=status_panel_height,
        expand=True,
        box=box.ROUNDED,
        padding=(0, 1),
    )

    status_grid = Table.grid(expand=True, padding=(0, 1))
    status_grid.add_column(width=sprite_width + 6)
    status_grid.add_column(ratio=1)
    status_grid.add_row(sprite_panel, stats_panel)
    sections = [status_grid]

    if compact:
        return Group(*sections)

    visible_events = _visible_events(pet_state, event_offset, event_limit)
    events_table = Table.grid(expand=True, padding=(0, 1))
    events_table.add_column(style="dim", width=16)
    events_table.add_column(ratio=1)
    if visible_events:
        for event in visible_events:
            events_table.add_row(
                event.timestamp.strftime("%Y-%m-%d %H:%M"),
                _event_text(event.message),
            )
    else:
        events_table.add_row("-", "Nothing yet.")

    sections.append(
        Panel(
            events_table,
            title="Events",
            subtitle=_events_subtitle(pet_state, event_offset, event_limit),
            border_style="dim",
            box=box.ROUNDED,
            padding=(0, 1),
        )
    )
    return Group(*sections)


def render_interactive_view(
    pet_state: PetState,
    selected_action: str,
    event_offset: int = 0,
    status_message: Text | None = None,
    animation_time: datetime | None = None,
    *,
    action_rows: tuple[tuple[str | None, str | None], ...] | None = None,
):
    sections = [
        render_status(pet_state, event_offset=event_offset, animation_time=animation_time),
        render_actions(pet_state, selected_action, action_rows=action_rows),
    ]
    if status_message is not None:
        sections.append(
            Panel(
                status_message,
                border_style="bright_black",
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )
    return Group(*sections)


def stat_bar(stat_name: str, value: int) -> Text:
    filled_units = max(0, min(10, round(value / 10)))
    empty_units = 10 - filled_units
    fill_style = _stat_bar_fill_style(stat_name, value)
    bar_text = Text()
    bar_text.append("█" * filled_units, style=fill_style)
    bar_text.append("░" * empty_units, style=fill_style)
    return bar_text


def stat_value(stat_name: str, value: int) -> Text:
    fill_style = _stat_bar_fill_style(stat_name, value)
    return Text(f"{value:>3}/100", style=fill_style)


def render_actions(
    pet_state: PetState,
    selected_action: str,
    *,
    action_rows: tuple[tuple[str | None, str | None], ...] | None = None,
) -> Panel:
    rows = action_rows if action_rows is not None else _default_alive_action_rows(pet_state)
    actions_table = Table.grid(expand=True)
    actions_table.add_column(ratio=1)
    actions_table.add_column(ratio=1)
    for left, right in rows:
        actions_table.add_row(
            _action_label(left, selected_action),
            _action_label(right, selected_action),
        )
    return Panel(
        actions_table,
        title="Actions",
        subtitle="← → move | ↑ ↓ scroll | Enter confirm",
        border_style="dim",
        box=box.ROUNDED,
        padding=(0, 1),
    )


def _default_alive_action_rows(pet_state: PetState) -> tuple[tuple[str | None, str | None], ...]:
    return (
        ("feed", "play"),
        (_lights_action_name(pet_state), "clean"),
        ("medicine", "quit"),
    )


def _mood_style(mood: str) -> str:
    if mood == "happy":
        return "green"
    if mood == "sad":
        return "red"
    if mood == "dead":
        return "bright_black"
    return "yellow"


def _stat_bar_fill_style(stat_name: str, value: int) -> str:
    if stat_name in ("hunger", "happiness", "health", "energy"):
        if value < 10:
            return "red"
        if value < 50:
            return "orange3"
        return "green"
    if value <= 35:
        return "red"
    if value >= 70:
        return STAT_BAR_FILL_HIGH.get(stat_name, "green")
    return STAT_BAR_FILL_MID.get(stat_name, "yellow")


def _action_label(action_name: str | None, selected_action: str) -> Text:
    if not action_name:
        return Text("")
    action_display_name = _action_display_name(action_name)
    action_text = f" {ACTION_EMOJI.get(action_name, '•')} {action_display_name} "
    lights_match = selected_action == "lights" and action_name in ("lights_on", "lights_off")
    if action_name == selected_action or lights_match:
        return Text(action_text, style="bold white on green")
    return Text(action_text, style="bold white")


def _visible_events(pet_state: PetState, event_offset: int, event_limit: int):
    if event_limit <= 0:
        return list()

    total_events = len(pet_state.events)
    if total_events <= event_limit:
        return pet_state.events

    max_offset = max(0, total_events - event_limit)
    safe_offset = max(0, min(event_offset, max_offset))
    return pet_state.events[safe_offset:safe_offset + event_limit]


def _events_subtitle(pet_state: PetState, event_offset: int, event_limit: int) -> str:
    total_events = len(pet_state.events)
    if total_events == 0:
        return "PgUp/PgDn scroll"

    max_offset = max(0, total_events - event_limit)
    safe_offset = max(0, min(event_offset, max_offset))
    start_index = safe_offset + 1
    end_index = min(total_events, safe_offset + event_limit)
    return f"{start_index}-{end_index} of {total_events} | PgUp/PgDn scroll"


def _event_text(message: str) -> Text:
    event_text = Text()
    event_text.append(f"{_event_emoji(message)} ", style="default")
    event_text.append(message, style=_event_style(message))
    return event_text


def _event_emoji(message: str) -> str:
    normalized_message = message.lower()
    for event_key, emoji in EVENT_EMOJI.items():
        if event_key in normalized_message:
            return emoji
    if "passed away" in normalized_message:
        return "🪦"
    if "fell ill" in normalized_message:
        return "🤒"
    if "underweight" in normalized_message or "overweight" in normalized_message:
        return "⚖️"
    if "medicine" in normalized_message:
        return "💊"
    if "recovered" in normalized_message:
        return "✅"
    return "📌"


def _event_style(message: str) -> str:
    normalized_message = message.lower()
    if "passed away" in normalized_message:
        return "bold red"
    if "needs cleaning" in normalized_message:
        return "yellow"
    if "grew into" in normalized_message:
        return "bold magenta"
    if "fell ill" in normalized_message or "medicine" in normalized_message:
        return "yellow"
    if "recovered" in normalized_message:
        return "green"
    return "white"


def _action_display_name(action_name: str) -> str:
    display_names = {
        "feed": "Feed",
        "play": "Play",
        "lights_off": "Lights Off",
        "lights_on": "Lights On",
        "clean": "Clean",
        "medicine": "Medicine",
        "quit": "Quit",
        "new_pet": "New pet",
    }
    return display_names.get(action_name, action_name.replace("_", " ").title())


def _lights_action_name(pet_state: PetState) -> str:
    if pet_state.is_asleep:
        return "lights_on"
    return "lights_off"
