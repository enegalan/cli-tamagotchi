from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum

FALLBACK_CHARACTER = "Cat"


class Rarity(str, Enum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


RARITY_DISPLAY = {
    Rarity.COMMON: "Common",
    Rarity.UNCOMMON: "Uncommon",
    Rarity.RARE: "Rare",
    Rarity.EPIC: "Epic",
    Rarity.LEGENDARY: "Legendary",
}


@dataclass(frozen=True)
class CharacterSpec:
    character_id: str
    rarity: Rarity
    roll_weight: int
    rich_style: str


CHARACTER_POOL: tuple[CharacterSpec, ...] = (
    CharacterSpec(character_id="Cat", rarity=Rarity.COMMON, roll_weight=80, rich_style="bright_cyan"),
    CharacterSpec(character_id="Fox", rarity=Rarity.RARE, roll_weight=20, rich_style="bright_magenta"),
)

_CHARACTER_RARITY: dict[str, Rarity] = {spec.character_id: spec.rarity for spec in CHARACTER_POOL}
_CHARACTER_WEIGHTS: tuple[tuple[str, int], ...] = tuple(
    (spec.character_id, spec.roll_weight) for spec in CHARACTER_POOL
)

CHARACTER_STYLE_BY_NAME: dict[str, str] = {spec.character_id: spec.rich_style for spec in CHARACTER_POOL}


def rarity_for_character(character_id: str) -> Rarity:
    return _CHARACTER_RARITY.get(character_id, Rarity.COMMON)


def rarity_display_for_character(character_id: str) -> str:
    return RARITY_DISPLAY[rarity_for_character(character_id)]


def character_status_label(character_id: str) -> str:
    return f"{character_id} ({rarity_display_for_character(character_id)})"


def roll_starting_character(rng: random.Random | None = None) -> str:
    random_source = rng if rng is not None else random.Random()
    character_ids = [pair[0] for pair in _CHARACTER_WEIGHTS]
    weights = [pair[1] for pair in _CHARACTER_WEIGHTS]
    chosen = random_source.choices(character_ids, weights=weights, k=1)[0]
    return chosen
