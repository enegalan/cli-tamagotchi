from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Tuple

from cli_tamagotchi.coding_activity import CodingActivity, drain_activity_jsonl
from cli_tamagotchi.models import PetState
from cli_tamagotchi.plugins.base import BasePlugin


class GitToolPlugin(BasePlugin):
    name = "git_tool"
    description = "Reacts to git hook events (commit, merge, rebase)"
    version = "0.1.0"
    events_jsonl_basename = "git_events.jsonl"

    def __init__(self) -> None:
        self._last_event_line = 0

    def _event_path(self) -> Path:
        path = self.events_jsonl_path()
        if path is None:
            raise RuntimeError("GitToolPlugin.events_jsonl_basename must be set")
        return path

    def on_load(self) -> None:
        path = self._event_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()

    def on_tick(self, pet_state: PetState, tick_time: datetime) -> None:
        self._last_event_line = drain_activity_jsonl(
            self._event_path(),
            pet_state,
            tick_time,
            self._last_event_line,
        )

    def on_external_event(self, event_type: str, data: dict[str, Any]) -> None:
        pass


def build_hook_event(args: list[str]) -> Optional[Tuple[Path, dict[str, object]]]:
    if len(args) < 2 or args[0].lower() != "git":
        return None
    sub = args[1].lower()
    if sub not in ("commit", "merge", "rebase"):
        return None
    activity = CodingActivity.SHIPPING if sub in ("commit", "merge") else CodingActivity.LOOPING
    path = GitToolPlugin.events_jsonl_path()
    if path is None:
        return None
    return (path, {"ts": time.time(), "activity": activity.value})
