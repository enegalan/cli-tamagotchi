from __future__ import annotations

from ..models import DEFAULT_CHARACTER
from ..models import STAGE_ADULT, STAGE_BABY, STAGE_CHILD, STAGE_DEAD, STAGE_EGG

SPRITES = {
    DEFAULT_CHARACTER: {
        STAGE_EGG: {
            "happy": ["   ____   ", "  / __ \\  ", " / /  \\_\\ ", " \\ \\__/ / ", "  \\____/  "],
            "neutral": ["   ____   ", "  / . .\\  ", " / /  \\_\\ ", " \\ \\__/ / ", "  \\____/  "],
            "sad": ["   ____   ", "  / - -\\  ", " / /  \\_\\ ", " \\ \\__/ / ", "  \\____/  "],
            "sleeping": ["   ____   ", "  / - -\\  ", " / /  \\_\\ ", " \\ \\__/ / ", "  \\____/  "],
        },
        STAGE_BABY: {
            "happy": ["  /\\_/\\ ", " ( ^.^ )", " /|___|\\", "  /   \\ "],
            "neutral": ["  /\\_/\\ ", " ( o.o )", " /|___|\\", "  /   \\ "],
            "sad": ["  /\\_/\\ ", " ( -.- )", " /|___|\\", "  /   \\ "],
            "sleeping": ["  /\\_/\\ ", " ( -.- )", " /|___|\\", "  /   \\ "],
        },
        STAGE_CHILD: {
            "happy": ["  /^ ^\\ ", " ( 0 0 )", " /  V  \\", "/|(___)|\\"],
            "neutral": ["  /^ ^\\ ", " ( o o )", " /  V  \\", "/|(___)|\\"],
            "sad": ["  /^ ^\\ ", " ( - - )", " /  V  \\", "/|(___)|\\"],
            "sleeping": ["  /^ ^\\ ", " ( - - )", " /  V  \\", "/|(___)|\\"],
        },
        STAGE_ADULT: {
            "happy": ["  /\\___/\\", " (  ^ ^  )", " /|  V  |\\", "/_|_____|_\\"],
            "neutral": ["  /\\___/\\", " (  o o  )", " /|  V  |\\", "/_|_____|_\\"],
            "sad": ["  /\\___/\\", " (  - -  )", " /|  V  |\\", "/_|_____|_\\"],
            "sleeping": ["  /\\___/\\", " (  - -  )", " /|  V  |\\", "/_|_____|_\\"],
        },
        STAGE_DEAD: {
            "dead": ["  x     x ", "    ___   ", "  /     \\", "  \\_____/ "],
            "sleeping": ["  x     x ", "    ___   ", "  /     \\", "  \\_____/ "],
        },
    },
}


def get_sprite_lines(character: str, stage: str, mood: str, is_asleep: bool = False) -> list[str]:
    character_sprites = SPRITES.get(character, SPRITES[DEFAULT_CHARACTER])
    stage_sprites = character_sprites[stage]
    if is_asleep:
        return stage_sprites.get("sleeping", stage_sprites.get(mood, stage_sprites["neutral"]))
    return stage_sprites[mood]
