from __future__ import annotations

from datetime import datetime

from ..characters import FALLBACK_CHARACTER
from ..models import STAGE_ADULT, STAGE_BABY, STAGE_CHILD, STAGE_DEAD, STAGE_EGG

FRAME_INTERVAL_MS = 550
REACTION_FRAME_INTERVAL_MS = 400

_CAT_SPRITES = {
    STAGE_EGG: {
        "happy": [
            ["   ____   ", "  /    \\  ", " / /  \\ \\ ", " \\ \\__/ / ", "  \\____/  "],
        ],
        "neutral": [
            ["   ____   ", "  /    \\  ", " / /  \\ \\ ", " \\ \\__/ / ", "  \\____/  "],
        ],
        "sad": [
            ["   ____   ", "  /    \\  ", " / /  \\ \\ ", " \\ \\__/ / ", "  \\____/  "],
        ],
        "sleeping": [
            ["   ____   ", "  /    \\  ", " / /  \\ \\ ", " \\ \\__/ / ", "  \\____/  "],
        ],
        "eating": [
            ["   ____   ", "  /    \\  ", " / /  \\ \\ ", " \\ \\__/ / ", "  \\____/  "],
        ],
        "playing": [
            ["   ____   ", "  /    \\  ", " / /  \\ \\ ", " \\ \\__/ / ", "  \\____/  "],
        ],
        "cleaning": [
            ["   ____   ", "  /    \\  ", " / /  \\ \\ ", " \\ \\__/ / ", "  \\____/  "],
        ],
    },
    STAGE_BABY: {
        "happy": [
            ["  /\\_/\\ ", " ( ^.^ )", " /|___|\\", "  /   \\ "],
            ["  /\\_/\\ ", " ( -.- )", " /|___|\\", "  /   \\ "],
        ],
        "neutral": [
            ["  /\\_/\\ ", " ( o.o )", " /|___|\\", "  /   \\ "],
            ["  /\\_/\\ ", " ( o-o )", " /|___|\\", "  /   \\ "],
        ],
        "sad": [
            ["  /\\_/\\ ", " ( -.- )", " /|___|\\", "  /   \\ "],
            ["  /\\_/\\ ", " ( ;.; )", " /|___|\\", "  /   \\ "],
        ],
        "sleeping": [
            ["  /\\_/\\ ", " ( -.- )", " /|___|\\", "  /   \\ "],
        ],
        "eating": [
            ["  /\\_/\\ ", " ( ^o^ )", " /|___|\\", "  /   \\ "],
            ["  /\\_/\\ ", " ( ^-^ )", " /|___|\\", "  /   \\ "],
        ],
        "playing": [
            ["  /\\_/\\ ", " ( ^o^ )", " /|___|\\", "  /   \\ "],
            ["  /\\_/\\ ", " ( >_< )", " /|___|\\", "  /   \\ "],
        ],
        "cleaning": [
            ["  /\\_/\\ ", " ( o.o )", " /|___|\\", "  /   \\ "],
            ["  /\\_/\\ ", " ( ^.^ )", " /|___|\\", "  /   \\ "],
        ],
    },
    STAGE_CHILD: {
        "happy": [
            ["  /^ ^\\ ", " ( o o )", " /  V  \\", "/|(___)|\\"],
            ["  /^ ^\\ ", " ( - - )", " /  V  \\", "/|(___)|\\"],
        ],
        "neutral": [
            ["  /^ ^\\ ", " ( o o )", " /  V  \\", "/|(___)|\\"],
            ["  /^ ^\\ ", " ( . . )", " /  V  \\", "/|(___)|\\"],
        ],
        "sad": [
            ["  /^ ^\\ ", " ( - - )", " /  V  \\", "/|(___)|\\"],
            ["  /^ ^\\ ", " ( ; ; )", " /  V  \\", "/|(___)|\\"],
        ],
        "sleeping": [
            ["  /^ ^\\ ", " ( - - )", " /  V  \\", "/|(___)|\\"],
            ["  /^ ^\\ ", " ( u u )", " /  V  \\", "/|(___)|\\"],
        ],
        "eating": [
            ["  /^ ^\\ ", " ( ^o^ )", " /  V  \\", "/|(___)|\\"],
            ["  /^ ^\\ ", " ( ^-^ )", " /  V  \\", "/|(___)|\\"],
        ],
        "playing": [
            ["  /^ ^\\ ", " ( >o< )", " /  V  \\", "/|(___)|\\"],
            ["  /^ ^\\ ", " ( ^o^ )", " /  V  \\", "/|(___)|\\"],
        ],
        "cleaning": [
            ["  /^ ^\\ ", " ( o o )", " / ~~  \\", "/|(___)|\\"],
            ["  /^ ^\\ ", " ( ^ ^ )", " /  V  \\", "/|(___)|\\"],
        ],
    },
    STAGE_ADULT: {
        "happy": [
            ["  /\\___/\\", " (  ^ ^  )", " /|  V  |\\", "/_|_____|_\\"],
            ["  /\\___/\\", " (  o o  )", " /|  V  |\\", "/_|_____|_\\"],
        ],
        "neutral": [
            ["  /\\___/\\", " (  o o  )", " /|  V  |\\", "/_|_____|_\\"],
            ["  /\\___/\\", " (  - -  )", " /|  V  |\\", "/_|_____|_\\"],
        ],
        "sad": [
            ["  /\\___/\\", " (  - -  )", " /|  V  |\\", "/_|_____|_\\"],
            ["  /\\___/\\", " (  ; ;  )", " /|  V  |\\", "/_|_____|_\\"],
        ],
        "sleeping": [
            ["  /\\___/\\", " (  - -  )", " /|  V  |\\", "/_|_____|_\\"],
            ["  /\\___/\\", " (  u u  )", " /|  V  |\\", "/_|_____|_\\"],
        ],
        "eating": [
            ["  /\\___/\\", " (  ^o^  )", " /|  V  |\\", "/_|_____|_\\"],
            ["  /\\___/\\", " (  ^-^  )", " /|  V  |\\", "/_|_____|_\\"],
        ],
        "playing": [
            ["  /\\___/\\", " (  >_<  )", " /|  V  |\\", "/_|_____|_\\"],
            ["  /\\___/\\", " (  ^o^  )", " /|  V  |\\", "/_|_____|_\\"],
        ],
        "cleaning": [
            ["  /\\___/\\", " (  o o  )", " /| ~~ |\\", "/_|_____|_\\"],
            ["  /\\___/\\", " (  ^ ^  )", " /|  V  |\\", "/_|_____|_\\"],
        ],
    },
    STAGE_DEAD: {
        "dead": [
            [
                "  /\\___/\\",
                " (  X.X  )",
                " /|     |\\",
                " _|_____|_",
            ],
        ],
    },
}

SPRITES = {
    "Cat": _CAT_SPRITES,
    "Fox": _CAT_SPRITES,
}


def _normalize_sprite_frames(raw_frames: list[list[str]]) -> list[list[str]]:
    if not raw_frames:
        return raw_frames
    max_height = max(len(frame) for frame in raw_frames)
    max_widths = [0] * max_height
    for frame in raw_frames:
        for row_index, line in enumerate(frame):
            max_widths[row_index] = max(max_widths[row_index], len(line))
    normalized: list[list[str]] = []
    for frame in raw_frames:
        padded_lines: list[str] = []
        for row_index in range(max_height):
            line = frame[row_index] if row_index < len(frame) else ""
            padded_lines.append(line.ljust(max_widths[row_index]))
        normalized.append(padded_lines)
    return normalized


def _frame_index(animation_time: datetime, frame_count: int, interval_ms: int) -> int:
    if frame_count <= 1:
        return 0
    timestamp_ms = int(animation_time.timestamp() * 1000)
    return (timestamp_ms // interval_ms) % frame_count


def _pick_sprite_frames(stage_sprites: dict[str, list[list[str]]], mood: str, *, is_asleep: bool) -> list[list[str]]:
    if is_asleep:
        preference_order = ("sleeping", mood, "neutral", "happy", "sad", "dead")
    else:
        preference_order = (mood, "neutral", "happy", "sad", "dead", "sleeping")
    for pose_key in preference_order:
        frames = stage_sprites.get(pose_key)
        if frames:
            return frames
    for _pose_key, frames in stage_sprites.items():
        if frames:
            return frames
    return [[""]]


def get_sprite_lines(
    character: str,
    stage: str,
    mood: str,
    is_asleep: bool = False,
    *,
    reaction_pose: str | None = None,
    animation_time: datetime | None = None,
) -> list[str]:
    character_sprites = SPRITES.get(character, SPRITES[FALLBACK_CHARACTER])
    stage_sprites = character_sprites.get(stage)
    if stage_sprites is None:
        stage_sprites = character_sprites[STAGE_EGG]
    use_reaction = (
        reaction_pose is not None
        and reaction_pose in stage_sprites
        and not is_asleep
    )
    if use_reaction:
        raw_frames = stage_sprites[reaction_pose]
        interval_ms = REACTION_FRAME_INTERVAL_MS
    else:
        raw_frames = _pick_sprite_frames(stage_sprites, mood, is_asleep=is_asleep)
        interval_ms = FRAME_INTERVAL_MS
    frames = _normalize_sprite_frames(raw_frames)
    if not frames:
        return list()
    if animation_time is None:
        return frames[0]
    frame_idx = _frame_index(animation_time, len(frames), interval_ms)
    return frames[frame_idx]
