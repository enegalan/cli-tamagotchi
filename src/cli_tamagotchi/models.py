from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .characters import CHARACTER_STYLE_BY_NAME
from .illnesses import illness_from_value

MAX_LOG_EVENTS = 50
REACTION_ANIMATION_WINDOW = timedelta(seconds=2.8)
STAGE_EGG = "Egg"
STAGE_BABY = "Baby"
STAGE_CHILD = "Child"
STAGE_ADULT = "Adult"
STAGE_DEAD = "Dead"
STAGE_STYLE_BY_NAME = {
    STAGE_EGG: "bright_white",
    STAGE_BABY: "bright_yellow",
    STAGE_CHILD: "bright_green",
    STAGE_ADULT: "bright_blue",
    STAGE_DEAD: "bright_black",
}


def clamp_stat(value: int) -> int:
    return max(0, min(100, value))


@dataclass
class EventEntry:
    timestamp: datetime
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, str]) -> "EventEntry":
        return cls(
            timestamp=datetime.fromisoformat(payload["timestamp"]),
            message=payload["message"],
        )


@dataclass
class ActiveIllness:
    illness_id: str
    ticks_remaining: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "illness_id": self.illness_id,
            "ticks_remaining": self.ticks_remaining,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ActiveIllness":
        raw_ticks = payload.get("ticks_remaining")
        ticks: int | None
        if raw_ticks is None:
            ticks = None
        else:
            ticks = int(raw_ticks)
        return cls(illness_id=str(payload["illness_id"]), ticks_remaining=ticks)


@dataclass
class PetState:
    name: str
    character: str
    stage: str
    weight: int
    hunger: int
    happiness: int
    health: int
    energy: int
    is_asleep: bool
    is_alive: bool
    dirtiness: int
    awake_minutes: int
    created_at: datetime
    stage_started_at: datetime
    updated_at: datetime
    last_interaction_at: datetime
    last_tick_at: datetime
    events: list[EventEntry] = field(default_factory=list)
    active_illnesses: list[ActiveIllness] = field(default_factory=list)
    last_medicine_at: datetime | None = None

    def add_event(self, message: str, now: datetime) -> None:
        self.events.append(EventEntry(timestamp=now, message=message))
        if len(self.events) > MAX_LOG_EVENTS:
            self.events = self.events[-MAX_LOG_EVENTS:]
        self.updated_at = now

    def has_illness_id(self, illness_id: str) -> bool:
        return any(entry.illness_id == illness_id for entry in self.active_illnesses)

    def average_stats(self) -> int:
        return round((self.hunger + self.happiness + self.health) / 3)

    def recent_events(self, limit: int = 5) -> list[EventEntry]:
        return self.events[-limit:]

    def mood(self) -> str:
        if not self.is_alive:
            return "dead"

        average_value = self.average_stats()
        if average_value >= 70:
            return "happy"
        if average_value <= 35:
            return "sad"
        return "neutral"

    def stage_age_hours(self) -> int:
        stage_age = self.updated_at - self.stage_started_at
        return max(0, int(stage_age.total_seconds() // 3600))

    def reaction_pose_id(self, now: datetime | None) -> str | None:
        if now is None:
            return None
        if not self.is_alive or self.stage == STAGE_DEAD:
            return None
        if self.is_asleep:
            return None
        if not self.events:
            return None
        last_entry = self.events[-1]
        if now - last_entry.timestamp > REACTION_ANIMATION_WINDOW:
            return None
        message_lower = last_entry.message.lower()
        if "you fed" in message_lower:
            return "eating"
        if "you played with" in message_lower:
            return "playing"
        if "you cleaned" in message_lower and "already" not in message_lower:
            return "cleaning"
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "character": self.character,
            "stage": self.stage,
            "weight": self.weight,
            "hunger": self.hunger,
            "happiness": self.happiness,
            "health": self.health,
            "energy": self.energy,
            "is_asleep": self.is_asleep,
            "is_alive": self.is_alive,
            "dirtiness": self.dirtiness,
            "awake_minutes": self.awake_minutes,
            "created_at": self.created_at.isoformat(),
            "stage_started_at": self.stage_started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_interaction_at": self.last_interaction_at.isoformat(),
            "last_tick_at": self.last_tick_at.isoformat(),
            "events": [event.to_dict() for event in self.events],
            "active_illnesses": [entry.to_dict() for entry in self.active_illnesses],
            "last_medicine_at": self.last_medicine_at.isoformat() if self.last_medicine_at else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PetState":
        last_medicine_raw = payload.get("last_medicine_at")
        last_medicine_at = datetime.fromisoformat(last_medicine_raw) if last_medicine_raw else None

        active_illnesses = [ActiveIllness.from_dict(item) for item in payload["active_illnesses"]]
        active_illnesses = _sanitize_active_illnesses(active_illnesses)

        return cls(
            name=payload["name"],
            character=payload["character"],
            stage=payload["stage"],
            weight=max(0, int(payload["weight"])),
            hunger=clamp_stat(payload["hunger"]),
            happiness=clamp_stat(payload["happiness"]),
            health=clamp_stat(payload["health"]),
            energy=clamp_stat(int(payload["energy"])),
            is_asleep=bool(payload["is_asleep"]),
            is_alive=bool(payload["is_alive"]),
            dirtiness=max(0, min(3, int(payload["dirtiness"]))),
            awake_minutes=max(0, int(payload["awake_minutes"])),
            created_at=datetime.fromisoformat(payload["created_at"]),
            stage_started_at=datetime.fromisoformat(payload["stage_started_at"]),
            updated_at=datetime.fromisoformat(payload["updated_at"]),
            last_interaction_at=datetime.fromisoformat(payload["last_interaction_at"]),
            last_tick_at=datetime.fromisoformat(payload["last_tick_at"]),
            events=[EventEntry.from_dict(event) for event in payload.get("events", list())],
            active_illnesses=active_illnesses,
            last_medicine_at=last_medicine_at,
        )


def _sanitize_active_illnesses(entries: list[ActiveIllness]) -> list[ActiveIllness]:
    cleaned: list[ActiveIllness] = list()
    seen: set[str] = set()
    for entry in entries:
        if entry.illness_id in seen:
            continue
        ill = illness_from_value(entry.illness_id)
        if ill is None:
            continue
        if entry.ticks_remaining is not None and entry.ticks_remaining <= 0:
            continue
        seen.add(entry.illness_id)
        cleaned.append(entry)
    return cleaned
