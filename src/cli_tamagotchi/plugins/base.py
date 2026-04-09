from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cli_tamagotchi.models import PetState


class BasePlugin:
    name: str = "unnamed_plugin"
    description: str = ""
    version: str = "0.1.0"
    events_jsonl_basename: str | None = None

    @classmethod
    def events_jsonl_path(cls) -> Path | None:
        """Path under the Tamagotchi data home for external JSONL events, if this plugin uses that pattern."""
        if not cls.events_jsonl_basename:
            return None
        from .manager import get_plugin_data_home

        return get_plugin_data_home() / cls.events_jsonl_basename

    def on_load(self) -> None:
        pass

    def on_unload(self) -> None:
        pass

    def on_tick(self, pet_state: "PetState", tick_time: datetime) -> None:
        pass

    def on_event(self, pet_state: "PetState", message: str, timestamp: datetime) -> None:
        pass

    def on_external_event(self, event_type: str, data: dict[str, Any]) -> None:
        pass

    def on_action(self, pet_state: "PetState", action: str, now: datetime) -> None:
        pass

    def on_stage_change(
        self,
        pet_state: "PetState",
        old_stage: str,
        new_stage: str,
        at: datetime,
    ) -> None:
        pass

    def on_death(self, pet_state: "PetState", cause: str) -> None:
        pass
