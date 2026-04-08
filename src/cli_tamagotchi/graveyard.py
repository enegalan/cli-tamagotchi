from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import PetState


@dataclass(frozen=True)
class GraveyardEntry:
    name: str
    character: str
    stage: str
    created_at: datetime
    died_at: datetime

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "character": self.character,
            "stage": self.stage,
            "created_at": self.created_at.isoformat(),
            "died_at": self.died_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> GraveyardEntry:
        raw_name = payload.get("name") or payload.get("pet_name") or ""
        name_stripped = str(raw_name).strip()
        return cls(
            name=name_stripped if name_stripped else "?",
            character=str(payload.get("character") or "?"),
            stage=str(payload.get("stage") or "Dead"),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            died_at=datetime.fromisoformat(str(payload["died_at"])),
        )


def snapshot_from_dead_pet(pet_state: PetState) -> GraveyardEntry:
    return GraveyardEntry(
        name=pet_state.name,
        character=pet_state.character,
        stage=pet_state.stage,
        created_at=pet_state.created_at,
        died_at=pet_state.stage_started_at,
    )


def read_graveyard(path: Path) -> list[GraveyardEntry]:
    if not path.exists():
        return list()
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries_raw = raw.get("entries", list())
    if not isinstance(entries_raw, list):
        return list()
    result: list[GraveyardEntry] = list()
    for item in entries_raw:
        if not isinstance(item, dict):
            continue
        try:
            result.append(GraveyardEntry.from_dict(item))
        except (KeyError, TypeError, ValueError):
            continue
    return result


def write_graveyard(path: Path, entries: list[GraveyardEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"entries": [entry.to_dict() for entry in entries]}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def append_graveyard_entry(path: Path, entry: GraveyardEntry) -> None:
    entries = read_graveyard(path)
    entries.append(entry)
    write_graveyard(path, entries)
