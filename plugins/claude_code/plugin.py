from __future__ import annotations

import json
import time
from collections import Counter, deque
from datetime import datetime
from pathlib import Path
from typing import Any

from cli_tamagotchi.models import PetState, clamp_stat
from cli_tamagotchi.plugins.base import BasePlugin


class AgentBehaviorClassifier:
    WINDOW = 20

    def __init__(self) -> None:
        self._tool_calls: deque[dict[str, Any]] = deque(maxlen=self.WINDOW)
        self._last_write_at: float = 0.0
        self._error_count = 0
        self._loop_counter: Counter[str] = Counter()

    def record_tool_call(self, tool: str, exit_code: int = 0) -> str:
        now = time.time()
        self._tool_calls.append({"tool": tool, "ts": now, "exit": exit_code})
        self._loop_counter[tool] += 1

        if tool in ("write_file", "edit_file", "bash") and exit_code == 0:
            self._last_write_at = now
            self._loop_counter.clear()

        if exit_code != 0:
            self._error_count += 1
        else:
            self._error_count = max(0, self._error_count - 1)

        return self.classify()

    def classify(self) -> str:
        if self._error_count >= 5:
            return "BLOCKED"
        if any(count >= 5 for count in self._loop_counter.values()):
            return "LOOPING"
        recent_tools = [e["tool"] for e in self._tool_calls]
        write_tools = {"write_file", "edit_file", "bash", "str_replace_editor"}
        read_tools = {"read_file", "list_dir", "grep", "glob"}
        writes = sum(1 for t in recent_tools if t in write_tools)
        reads = sum(1 for t in recent_tools if t in read_tools)
        if writes > reads:
            return "SHIPPING"
        if reads > 5 and writes == 0:
            return "EXPLORING"
        return "WORKING"


BEHAVIOR_REACTIONS: dict[str, dict[str, int]] = {
    "SHIPPING": {"happy_delta": 1, "hunger_delta": 0},
    "LOOPING": {"happy_delta": -1, "hunger_delta": -1},
    "EXPLORING": {"happy_delta": 0, "hunger_delta": 0},
    "BLOCKED": {"happy_delta": -1, "hunger_delta": -1},
    "WORKING": {"happy_delta": 0, "hunger_delta": 0},
    "DONE_SUCCESS": {"happy_delta": 2, "hunger_delta": 1},
    "DONE_FAILURE": {"happy_delta": -1, "hunger_delta": -1},
    "TESTS_PASSED": {"happy_delta": 2, "hunger_delta": 1},
    "TESTS_FAILED": {"happy_delta": -1, "hunger_delta": 0},
}


def _apply_reaction(pet_state: PetState, key: str) -> None:
    reaction = BEHAVIOR_REACTIONS.get(key, BEHAVIOR_REACTIONS["WORKING"])
    pet_state.happiness = clamp_stat(pet_state.happiness + reaction["happy_delta"] * 15)
    pet_state.hunger = clamp_stat(pet_state.hunger + reaction["hunger_delta"] * 12)


class ClaudeCodePlugin(BasePlugin):
    name = "claude_code"
    description = "Reacts to Claude Code agent behavior"
    version = "0.1.0"
    events_jsonl_basename = "claude_events.jsonl"

    def __init__(self) -> None:
        self._classifier = AgentBehaviorClassifier()
        self._last_event_line = 0
        self._last_behavior = "WORKING"
        self._behavior_tick = 0

    def _event_path(self) -> Path:
        path = self.events_jsonl_path()
        if path is None:
            raise RuntimeError("ClaudeCodePlugin.events_jsonl_basename must be set")
        return path

    def on_load(self) -> None:
        path = self._event_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()

    def on_tick(self, pet_state: PetState, tick_time: datetime) -> None:
        self._poll_events(pet_state)
        self._behavior_tick += 1
        if self._behavior_tick % 60 == 0:
            _apply_reaction(pet_state, self._last_behavior)

    def _poll_events(self, pet_state: PetState) -> None:
        path = self._event_path()
        if not path.exists():
            return
        lines = path.read_text(encoding="utf-8").splitlines()
        new_lines = lines[self._last_event_line :]
        self._last_event_line = len(lines)

        for line in new_lines:
            try:
                event = json.loads(line)
                self._process_event(pet_state, event)
            except (json.JSONDecodeError, TypeError, ValueError, KeyError):
                pass

    def _process_event(self, pet_state: PetState, event: dict[str, Any]) -> None:
        etype = event.get("type", "")
        if etype == "pre_tool":
            return
        if etype == "post_tool":
            tool = event.get("tool", "unknown")
            exit_code = int(event.get("exit_code", 0))
            behavior = self._classifier.record_tool_call(tool, exit_code)
            self._last_behavior = behavior
            if tool == "bash" and "pytest" in event.get("command", ""):
                if exit_code == 0:
                    _apply_reaction(pet_state, "TESTS_PASSED")
                else:
                    _apply_reaction(pet_state, "TESTS_FAILED")
        elif etype == "stop":
            reason = event.get("reason", "")
            if reason in ("task_complete", "success"):
                _apply_reaction(pet_state, "DONE_SUCCESS")
            else:
                _apply_reaction(pet_state, "DONE_FAILURE")
        elif etype == "subagent_start":
            pet_state.happiness = clamp_stat(pet_state.happiness - 12)

    def on_external_event(self, event_type: str, data: dict[str, Any]) -> None:
        pass


def build_hook_event(args: list[str]) -> tuple[Path, dict[str, object]] | None:
    """Parse ``tama-hook`` argv for Claude Code; return None if these are not Claude commands."""
    if not args:
        return None

    payload: dict[str, object] = {"ts": time.time()}
    command = args[0]

    if command == "pre-tool" and len(args) >= 2:
        payload.update({"type": "pre_tool", "tool": args[1]})
    elif command == "post-tool" and len(args) >= 3:
        payload.update(
            {
                "type": "post_tool",
                "tool": args[1],
                "exit_code": int(args[2]),
                "command": " ".join(args[3:]) if len(args) > 3 else "",
            }
        )
    elif command == "stop" and len(args) >= 2:
        payload.update({"type": "stop", "reason": args[1]})
    elif command == "subagent-start":
        payload.update({"type": "subagent_start"})
    else:
        return None

    path = ClaudeCodePlugin.events_jsonl_path()
    if path is None:
        return None
    return (path, payload)
