from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import (
    DEFAULT_CHARACTER,
    PetState,
    STAGE_ADULT,
    STAGE_BABY,
    STAGE_CHILD,
    STAGE_DEAD,
    STAGE_EGG,
    clamp_stat,
)

TICK_MINUTES = 30
DIRTINESS_TICK_INTERVAL = 4
TIREDNESS_THRESHOLD_MINUTES = 12 * 60
STAGE_THRESHOLDS = (
    (timedelta(hours=1), STAGE_EGG),
    (timedelta(days=1), STAGE_BABY),
    (timedelta(days=3), STAGE_CHILD),
)


@dataclass
class ActionResult:
    pet_state: PetState
    message: str


def stage_for_age(age: timedelta, is_alive: bool) -> str:
    if not is_alive:
        return STAGE_DEAD

    for threshold, stage in STAGE_THRESHOLDS:
        if age < threshold:
            return stage
    return STAGE_ADULT


def create_new_pet(now: datetime, name: str) -> PetState:
    pet_state = PetState(
        name=name,
        character=DEFAULT_CHARACTER,
        stage=STAGE_EGG,
        weight=5,
        hunger=80,
        happiness=75,
        health=90,
        is_asleep=False,
        is_alive=True,
        dirtiness=0,
        awake_minutes=0,
        created_at=now,
        stage_started_at=now,
        updated_at=now,
        last_interaction_at=now,
        last_tick_at=now,
        events=list(),
    )
    pet_state.add_event("A new egg has hatched.", now)
    return pet_state


def reconcile_state(pet_state: PetState, now: datetime) -> PetState:
    if now <= pet_state.last_tick_at:
        pet_state.stage = stage_for_age(now - pet_state.created_at, pet_state.is_alive)
        pet_state.updated_at = now
        return pet_state

    if not pet_state.is_alive:
        pet_state.stage = STAGE_DEAD
        pet_state.updated_at = now
        return pet_state

    elapsed = now - pet_state.last_tick_at
    tick_count = int(elapsed.total_seconds() // (TICK_MINUTES * 60))
    stage_before = pet_state.stage

    for tick_index in range(tick_count):
        tick_time = pet_state.last_tick_at + timedelta(minutes=TICK_MINUTES * (tick_index + 1))
        _apply_tick(pet_state, tick_time)
        new_stage = stage_for_age(tick_time - pet_state.created_at, pet_state.is_alive)
        if new_stage != pet_state.stage:
            pet_state.stage = new_stage
            pet_state.stage_started_at = tick_time
            if pet_state.is_alive:
                pet_state.add_event(f"{pet_state.name} grew into a {new_stage.lower()}.", tick_time)
        if not pet_state.is_alive:
            pet_state.stage = STAGE_DEAD
            pet_state.stage_started_at = tick_time
            break

    pet_state.last_tick_at = pet_state.last_tick_at + timedelta(minutes=tick_count * TICK_MINUTES)
    pet_state.updated_at = now

    if tick_count == 0 and stage_before != pet_state.stage:
        pet_state.add_event(f"{pet_state.name} grew into a {pet_state.stage.lower()}.", now)

    return pet_state


def apply_action(pet_state: PetState, action: str, now: datetime) -> ActionResult:
    reconcile_state(pet_state, now)
    normalized_action = action.strip().lower()

    if not pet_state.is_alive:
        pet_state.updated_at = now
        return ActionResult(pet_state=pet_state, message=f"{pet_state.name} can no longer respond.")

    action_messages = {
        "feed": _feed_pet,
        "play": _play_with_pet,
        "lights": _toggle_lights,
        "clean": _clean_pet,
    }

    if normalized_action not in action_messages:
        raise ValueError(f"Unsupported action: {action}")

    message = action_messages[normalized_action](pet_state, now)
    pet_state.last_interaction_at = now
    pet_state.updated_at = now
    return ActionResult(pet_state=pet_state, message=message)


def _apply_tick(pet_state: PetState, tick_time: datetime) -> None:
    if pet_state.is_asleep:
        pet_state.hunger = clamp_stat(pet_state.hunger - 1)
        pet_state.awake_minutes = 0
        if pet_state.hunger >= 30:
            pet_state.health = clamp_stat(pet_state.health + 1)
    else:
        pet_state.hunger = clamp_stat(pet_state.hunger - 3)
        pet_state.happiness = clamp_stat(pet_state.happiness - 2)
        pet_state.awake_minutes += TICK_MINUTES

        if pet_state.awake_minutes % (DIRTINESS_TICK_INTERVAL * TICK_MINUTES) == 0:
            pet_state.dirtiness = min(3, pet_state.dirtiness + 1)
            pet_state.add_event(f"{pet_state.name} needs cleaning.", tick_time)

        if pet_state.awake_minutes >= TIREDNESS_THRESHOLD_MINUTES + (4 * TICK_MINUTES):
            pet_state.health = clamp_stat(pet_state.health - 2)

    if pet_state.hunger <= 15:
        pet_state.health = clamp_stat(pet_state.health - 3)
    if pet_state.happiness <= 15:
        pet_state.health = clamp_stat(pet_state.health - 2)
    if pet_state.dirtiness >= 3:
        pet_state.health = clamp_stat(pet_state.health - 1)

    if pet_state.health == 0:
        pet_state.is_alive = False
        pet_state.stage = STAGE_DEAD
        pet_state.stage_started_at = tick_time
        pet_state.add_event(f"{pet_state.name} has passed away.", tick_time)


def _feed_pet(pet_state: PetState, now: datetime) -> str:
    pet_state.hunger = clamp_stat(pet_state.hunger + 25)
    pet_state.happiness = clamp_stat(pet_state.happiness + 4)
    pet_state.weight += 1
    pet_state.add_event(f"You fed {pet_state.name}.", now)
    return f"You fed {pet_state.name}."


def _play_with_pet(pet_state: PetState, now: datetime) -> str:
    if pet_state.is_asleep:
        return f"{pet_state.name} is asleep. Turn the lights on before playing."

    pet_state.happiness = clamp_stat(pet_state.happiness + 18)
    pet_state.hunger = clamp_stat(pet_state.hunger - 6)
    pet_state.health = clamp_stat(pet_state.health + 2)
    pet_state.weight = max(1, pet_state.weight - 1)
    pet_state.add_event(f"You played with {pet_state.name}.", now)
    return f"You played with {pet_state.name}."


def _toggle_lights(pet_state: PetState, now: datetime) -> str:
    if pet_state.is_asleep:
        pet_state.is_asleep = False
        pet_state.add_event(f"You turned the lights on for {pet_state.name}.", now)
        return f"You turned the lights on for {pet_state.name}."

    pet_state.is_asleep = True
    pet_state.awake_minutes = 0
    pet_state.add_event(f"You turned the lights off for {pet_state.name}.", now)
    return f"You turned the lights off for {pet_state.name}."


def _clean_pet(pet_state: PetState, now: datetime) -> str:
    if pet_state.dirtiness == 0:
        pet_state.add_event(f"{pet_state.name}'s space is already clean.", now)
        return f"{pet_state.name}'s space is already clean."

    pet_state.dirtiness = 0
    pet_state.health = clamp_stat(pet_state.health + 6)
    pet_state.add_event(f"You cleaned {pet_state.name}'s space.", now)
    return f"You cleaned {pet_state.name}'s space."
