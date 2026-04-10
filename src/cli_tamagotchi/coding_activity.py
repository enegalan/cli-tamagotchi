"""Canonical coding / agent activity labels and pet reactions (Phase 2 core)."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from .models import PetState, clamp_stat
from .pet_memory import followups_then_record, project_label

# Log prefix so TUI can show a brief reaction pose without ambiguous substring matches.
CODING_TAG_PREFIX = "[coding "
CODING_TAG_SUFFIX = "] "


class CodingActivity(str, Enum):
    SHIPPING = "shipping"
    LOOPING = "looping"
    EXPLORING = "exploring"
    BLOCKED = "blocked"
    TESTS_PASSED = "tests_passed"
    TESTS_FAILED = "tests_failed"
    SUB_AGENT_SPAWNED = "sub_agent_spawned"


# Tuple: (happiness step, hunger step) multiplied by _HAPPY_SCALE / _HUNGER_SCALE below.
_ACTIVITY_STEPS: dict[CodingActivity, tuple[int, int]] = {
    CodingActivity.SHIPPING: (1, 0),
    CodingActivity.LOOPING: (-1, -1),
    CodingActivity.EXPLORING: (0, 0),
    CodingActivity.BLOCKED: (-1, -1),
    CodingActivity.TESTS_PASSED: (2, 1),
    CodingActivity.TESTS_FAILED: (-1, 0),
    CodingActivity.SUB_AGENT_SPAWNED: (-1, 0),
}

_HAPPY_SCALE = 15
_HUNGER_SCALE = 12

_LOG_LINES: dict[CodingActivity, str] = {
    CodingActivity.SHIPPING: "{name} picks up momentum as changes land.",
    CodingActivity.LOOPING: "{name} senses you're going in circles.",
    CodingActivity.EXPLORING: "{name} watches you map the codebase.",
    CodingActivity.BLOCKED: "{name} feels the friction.",
    CodingActivity.TESTS_PASSED: "{name} cheers for green tests.",
    CodingActivity.TESTS_FAILED: "{name} flinches at a red run.",
    CodingActivity.SUB_AGENT_SPAWNED: "{name} spots another agent in the mix.",
}


def apply_coding_activity_reaction(
    pet_state: PetState,
    activity: CodingActivity,
    now: datetime,
    *,
    log_event: bool = True,
) -> None:
    """Adjust stats; optionally append a tagged log line for TUI reaction poses."""
    if not pet_state.is_alive:
        return
    happy_step, hunger_step = _ACTIVITY_STEPS[activity]
    pet_state.happiness = clamp_stat(pet_state.happiness + happy_step * _HAPPY_SCALE)
    pet_state.hunger = clamp_stat(pet_state.hunger + hunger_step * _HUNGER_SCALE)
    pet_state.updated_at = now
    label = project_label()
    extras = followups_then_record(
        pet_state.name,
        now,
        activity.value,
        label,
        emit_log=log_event,
    )
    if log_event:
        for note in extras:
            pet_state.add_event(note, now)
        body = _LOG_LINES[activity].format(name=pet_state.name)
        pet_state.add_event(f"{CODING_TAG_PREFIX}{activity.value}{CODING_TAG_SUFFIX}{body}", now)


def parse_coding_activity(value: object) -> CodingActivity | None:
    """Resolve a string to a member (e.g. from JSON or CLI); unknown values return None."""
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower().replace("-", "_")
    for member in CodingActivity:
        if member.value == normalized:
            return member
    return None


def drain_activity_jsonl(
    path: Path,
    pet_state: PetState,
    when: datetime,
    previous_line_count: int,
) -> int:
    """Apply reactions for new JSONL lines (``activity`` + optional ``silent``). Returns total line count."""
    if not path.exists():
        return previous_line_count
    lines = path.read_text(encoding="utf-8").splitlines()
    total = len(lines)
    for line in lines[previous_line_count:]:
        try:
            obj: Any = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(obj, dict):
            continue
        activity = parse_coding_activity(obj.get("activity"))
        if activity is None:
            continue
        silent = bool(obj.get("silent"))
        apply_coding_activity_reaction(pet_state, activity, when, log_event=not silent)
    return total


def coding_reaction_pose_id(message_lower: str) -> str | None:
    """Map a tagged coding log line to an existing sprite pose (no new art)."""
    if "[coding shipping]" in message_lower or "[coding tests_passed]" in message_lower:
        return "playing"
    if "[coding exploring]" in message_lower or "[coding sub_agent_spawned]" in message_lower:
        return "playing"
    return None
