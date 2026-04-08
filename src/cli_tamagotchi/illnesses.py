from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from random import Random

LOW_HEALTH_ILLNESS_THRESHOLD = 40
ILLNESS_CONTRACT_CHANCE_MAX = 0.22
MEDICINE_COOLDOWN = timedelta(hours=1)
MEDICINE_HEAL_FRACTION = 0.15


class Illness(Enum):
    SNIFFLES = "sniffles"
    COLD = "cold"
    FEVER = "fever"
    STOMACH_BUG = "stomach_bug"
    UNDERWEIGHT = "underweight"
    OVERWEIGHT = "overweight"


@dataclass(frozen=True)
class IllnessDefinition:
    display_name: str
    contraction_weight: float
    duration_ticks: int
    hunger_drain_per_tick: int
    happiness_drain_per_tick: int
    health_drain_per_tick: int
    weight_linked: bool = False
    extra_energy_drain_awake: int = 0
    extra_health_drain_per_tick: int = 0
    random_illness_chance_multiplier: float = 1.0
    play_health_cost: int = 0


ILLNESS_DEFINITION_BY_ENUM: dict[Illness, IllnessDefinition] = {
    Illness.SNIFFLES: IllnessDefinition(
        display_name="Sniffles",
        contraction_weight=0.32,
        duration_ticks=4,
        hunger_drain_per_tick=0,
        happiness_drain_per_tick=1,
        health_drain_per_tick=0,
    ),
    Illness.COLD: IllnessDefinition(
        display_name="Cold",
        contraction_weight=0.28,
        duration_ticks=8,
        hunger_drain_per_tick=1,
        happiness_drain_per_tick=2,
        health_drain_per_tick=1,
    ),
    Illness.FEVER: IllnessDefinition(
        display_name="Fever",
        contraction_weight=0.22,
        duration_ticks=6,
        hunger_drain_per_tick=2,
        happiness_drain_per_tick=2,
        health_drain_per_tick=2,
    ),
    Illness.STOMACH_BUG: IllnessDefinition(
        display_name="Stomach bug",
        contraction_weight=0.18,
        duration_ticks=5,
        hunger_drain_per_tick=3,
        happiness_drain_per_tick=1,
        health_drain_per_tick=1,
    ),
    Illness.UNDERWEIGHT: IllnessDefinition(
        display_name="Underweight",
        contraction_weight=0.0,
        duration_ticks=0,
        hunger_drain_per_tick=2,
        happiness_drain_per_tick=1,
        health_drain_per_tick=3,
        weight_linked=True,
        extra_energy_drain_awake=12,
        extra_health_drain_per_tick=4,
        random_illness_chance_multiplier=2.0,
        play_health_cost=6,
    ),
    Illness.OVERWEIGHT: IllnessDefinition(
        display_name="Overweight",
        contraction_weight=0.0,
        duration_ticks=0,
        hunger_drain_per_tick=1,
        happiness_drain_per_tick=1,
        health_drain_per_tick=4,
        weight_linked=True,
        extra_energy_drain_awake=12,
        extra_health_drain_per_tick=3,
        random_illness_chance_multiplier=2.0,
        play_health_cost=0,
    ),
}


def illness_from_value(value: str | None) -> Illness | None:
    if not value:
        return None
    try:
        return Illness(value)
    except ValueError:
        return None


def illness_contraction_chance(health: int, active_illness_ids: list[str]) -> float:
    if health > LOW_HEALTH_ILLNESS_THRESHOLD:
        return 0.0
    strain = (LOW_HEALTH_ILLNESS_THRESHOLD - health) / float(LOW_HEALTH_ILLNESS_THRESHOLD)
    base = min(ILLNESS_CONTRACT_CHANCE_MAX, ILLNESS_CONTRACT_CHANCE_MAX * strain)
    multiplier = 1.0
    for illness_id in active_illness_ids:
        ill = illness_from_value(illness_id)
        if ill is None:
            continue
        multiplier *= ILLNESS_DEFINITION_BY_ENUM[ill].random_illness_chance_multiplier
    return min(0.5, base * multiplier)


def pick_random_illness(rng: Random, active_illness_ids: set[str]) -> Illness | None:
    eligible = [
        illness
        for illness in Illness
        if not ILLNESS_DEFINITION_BY_ENUM[illness].weight_linked
        and ILLNESS_DEFINITION_BY_ENUM[illness].contraction_weight > 0
        and illness.value not in active_illness_ids
    ]
    if not eligible:
        return None
    weights = [ILLNESS_DEFINITION_BY_ENUM[illness].contraction_weight for illness in eligible]
    return rng.choices(eligible, weights=weights, k=1)[0]
