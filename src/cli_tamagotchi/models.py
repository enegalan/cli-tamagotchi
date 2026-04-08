from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .characters import CHARACTER_STYLE_BY_NAME, FALLBACK_CHARACTER

MAX_LOG_EVENTS = 50
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
class PetState:
    name: str
    character: str
    stage: str
    weight: int
    hunger: int
    happiness: int
    health: int
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

    def add_event(self, message: str, now: datetime) -> None:
        self.events.append(EventEntry(timestamp=now, message=message))
        if len(self.events) > MAX_LOG_EVENTS:
            self.events = self.events[-MAX_LOG_EVENTS:]
        self.updated_at = now

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "character": self.character,
            "stage": self.stage,
            "weight": self.weight,
            "hunger": self.hunger,
            "happiness": self.happiness,
            "health": self.health,
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
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PetState":
        return cls(
            name=payload["name"],
            character=payload.get("character", FALLBACK_CHARACTER),
            stage=payload["stage"],
            weight=max(0, int(payload.get("weight", 5))),
            hunger=clamp_stat(payload["hunger"]),
            happiness=clamp_stat(payload["happiness"]),
            health=clamp_stat(payload["health"]),
            is_asleep=bool(payload["is_asleep"]),
            is_alive=bool(payload["is_alive"]),
            dirtiness=max(0, min(3, int(payload["dirtiness"]))),
            awake_minutes=max(0, int(payload["awake_minutes"])),
            created_at=datetime.fromisoformat(payload["created_at"]),
            stage_started_at=datetime.fromisoformat(payload.get("stage_started_at", payload["created_at"])),
            updated_at=datetime.fromisoformat(payload["updated_at"]),
            last_interaction_at=datetime.fromisoformat(payload["last_interaction_at"]),
            last_tick_at=datetime.fromisoformat(payload["last_tick_at"]),
            events=[EventEntry.from_dict(event) for event in payload.get("events", list())],
        )
