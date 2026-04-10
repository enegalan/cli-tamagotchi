"""Lightweight cross-session hints from past coding activity (bounded JSON, no DB)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_MAX_RECENT = 12
_RECALL_WINDOW = timedelta(days=7)
_FAIL_ACTIVITIES = frozenset({"tests_failed", "blocked"})


def memory_file_path() -> Path:
    custom = os.environ.get("CLI_TAMAGOTCHI_HOME")
    base = Path(custom).expanduser() if custom else Path.home() / ".cli-tamagotchi"
    return base / "project_memory.json"


def project_label() -> str:
    env = os.environ.get("CLI_TAMAGOTCHI_PROJECT", "").strip()
    if env:
        return env[:64]
    try:
        name = Path.cwd().name.strip()
        return name[:64] if name else "this folder"
    except OSError:
        return "here"


def _activity_phrase(value: str) -> str:
    return {
        "shipping": "about shipping",
        "looping": "loop-heavy",
        "exploring": "exploratory",
        "blocked": "blocked",
        "tests_passed": "green tests",
        "tests_failed": "failing tests",
        "sub_agent_spawned": "multi-agent",
    }.get(value, value.replace("_", " "))


def _load_recent(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, TypeError):
        return []
    recent = raw.get("recent")
    if not isinstance(recent, list):
        return []
    out: list[dict[str, Any]] = []
    for item in recent:
        if isinstance(item, dict):
            out.append(item)
    return out


def _save_recent(path: Path, recent: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"recent": recent}, separators=(",", ":")) + "\n", encoding="utf-8")


def followups_then_record(
    pet_name: str,
    now: datetime,
    activity_value: str,
    label: str,
    *,
    emit_log: bool,
) -> list[str]:
    """
    Using stored recent activity for ``label``, build 0-1 recall lines, then append this activity.
    Followups are only computed when ``emit_log`` is True (matches visible coding events).
    """
    path = memory_file_path()
    recent = _load_recent(path)
    messages: list[str] = []

    same_label = [e for e in recent if str(e.get("label", "")) == label]

    if emit_log:
        if activity_value in _FAIL_ACTIVITIES and len(same_label) >= 2:
            last_two = same_label[-2:]
            if all(str(x.get("activity", "")) in _FAIL_ACTIVITIES for x in last_two):
                messages.append(
                    f"{pet_name} remembers {label} has been rough lately — same kind of snag again."
                )
        elif len(same_label) >= 1:
            last = same_label[-1]
            if str(last.get("activity", "")) != activity_value:
                try:
                    last_at = datetime.fromisoformat(str(last.get("at", "")))
                except (TypeError, ValueError):
                    last_at = None
                if last_at is not None and (now - last_at) <= _RECALL_WINDOW:
                    past = _activity_phrase(str(last.get("activity", "")))
                    messages.append(
                        f"{pet_name} recalls last time in {label}: it felt more {past}."
                    )

    entry = {"at": now.isoformat(), "activity": activity_value, "label": label}
    recent.append(entry)
    recent = recent[-_MAX_RECENT:]
    _save_recent(path, recent)
    return messages
