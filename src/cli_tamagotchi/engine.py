from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import random as random_module
from random import Random

from .characters import healthy_weight_bounds, roll_starting_character
from .illnesses import (
    ILLNESS_DEFINITION_BY_ENUM,
    MEDICINE_COOLDOWN,
    MEDICINE_HEAL_FRACTION,
    Illness,
    illness_contraction_chance,
    illness_from_value,
    pick_random_illness,
)
from .models import (
    ActiveIllness,
    PetState,
    STAGE_ADULT,
    STAGE_BABY,
    STAGE_CHILD,
    STAGE_DEAD,
    STAGE_EGG,
    clamp_stat,
    death_morph_for_live_stage,
)
from .plugins.manager import emit_plugin_event

TICK_MINUTES = 0.25
DIRTINESS_TICK_INTERVAL = 2
TIREDNESS_THRESHOLD_MINUTES = 12 * 60
STAGE_THRESHOLDS = (
    (timedelta(hours=1), STAGE_EGG),
    (timedelta(days=1), STAGE_BABY),
    (timedelta(days=3), STAGE_CHILD),
)

PLAY_BASE_ENERGY_COST = 14
IDLE_ENERGY_DRAIN_BASE = 1
SLEEP_ENERGY_GAIN_BASE = 10
ENERGY_WEIGHT_FACTOR = 0.042
SLUGGISH_WEIGHT_OFFSET = 6

DEFAULT_PET_NAMES = (
    "Byte",
    "Pixel",
    "Patch",
    "Kernel",
    "Glitch",
    "Stack",
    "Cache",
    "Qubit",
    "Node",
    "Echo",
    "Chip",
    "Hex",
    "Sprite",
    "Nibble",
    "Lambda",
    "Daemon",
    "Semicolon",
    "Bitty",
)


def pick_random_pet_name(rng: Random | None = None) -> str:
    if rng is not None:
        return rng.choice(DEFAULT_PET_NAMES)
    return random_module.choice(DEFAULT_PET_NAMES)


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


def _weight_energy_multiplier(pet_state: PetState) -> float:
    weight_min, weight_max = healthy_weight_bounds(pet_state.character)
    midpoint = (weight_min + weight_max) / 2.0
    weight_value = float(pet_state.weight)
    if weight_value < weight_min:
        return 1.0 + (weight_min - weight_value) * ENERGY_WEIGHT_FACTOR * 1.15
    if weight_value > weight_max:
        return 1.0 + (weight_value - weight_max) * ENERGY_WEIGHT_FACTOR * 1.15
    return 1.0 + abs(weight_value - midpoint) * ENERGY_WEIGHT_FACTOR * 0.35


def _play_energy_cost(pet_state: PetState) -> int:
    multiplier = _weight_energy_multiplier(pet_state)
    if pet_state.has_illness_id(Illness.UNDERWEIGHT.value) or pet_state.has_illness_id(Illness.OVERWEIGHT.value):
        multiplier *= 1.55
    return max(5, int(PLAY_BASE_ENERGY_COST * multiplier))


def _apply_awake_energy_drain(pet_state: PetState) -> None:
    drain = max(1, int(IDLE_ENERGY_DRAIN_BASE * _weight_energy_multiplier(pet_state)))
    for entry in pet_state.active_illnesses:
        ill = illness_from_value(entry.illness_id)
        if ill is None:
            continue
        drain += ILLNESS_DEFINITION_BY_ENUM[ill].extra_energy_drain_awake
    pet_state.energy = clamp_stat(pet_state.energy - drain)


def _apply_sleep_energy_gain(pet_state: PetState) -> None:
    # Softer weight penalty while asleep so rest actually refills energy in reasonable time.
    divisor = max(0.48, _weight_energy_multiplier(pet_state) * 0.55)
    gain = max(6, int(SLEEP_ENERGY_GAIN_BASE / divisor))
    pet_state.energy = clamp_stat(pet_state.energy + gain)


def _sync_weight_linked_illnesses(pet_state: PetState, now: datetime) -> None:
    weight_min, weight_max = healthy_weight_bounds(pet_state.character)
    active_ids = {entry.illness_id for entry in pet_state.active_illnesses}

    if pet_state.weight < weight_min:
        if Illness.UNDERWEIGHT.value not in active_ids:
            pet_state.active_illnesses.append(ActiveIllness(Illness.UNDERWEIGHT.value, None))
            pet_state.add_event(f"{pet_state.name} is dangerously underweight.", now)
    else:
        _remove_illness_by_id(pet_state, Illness.UNDERWEIGHT.value, now, "is no longer underweight")

    if pet_state.weight > weight_max:
        if Illness.OVERWEIGHT.value not in active_ids:
            pet_state.active_illnesses.append(ActiveIllness(Illness.OVERWEIGHT.value, None))
            pet_state.add_event(f"{pet_state.name} is dangerously overweight.", now)
    else:
        _remove_illness_by_id(pet_state, Illness.OVERWEIGHT.value, now, "is back to a healthier weight")


def _remove_illness_by_id(pet_state: PetState, illness_id: str, now: datetime, recovery_detail: str) -> None:
    before = len(pet_state.active_illnesses)
    pet_state.active_illnesses = [entry for entry in pet_state.active_illnesses if entry.illness_id != illness_id]
    if len(pet_state.active_illnesses) < before:
        pet_state.add_event(f"{pet_state.name} recovered ({recovery_detail}).", now)


def _process_active_illnesses(pet_state: PetState, tick_time: datetime) -> None:
    updated: list[ActiveIllness] = list()
    for entry in pet_state.active_illnesses:
        ill = illness_from_value(entry.illness_id)
        if ill is None:
            continue
        spec = ILLNESS_DEFINITION_BY_ENUM[ill]
        pet_state.hunger = clamp_stat(pet_state.hunger - spec.hunger_drain_per_tick)
        pet_state.happiness = clamp_stat(pet_state.happiness - spec.happiness_drain_per_tick)
        total_health_loss = spec.health_drain_per_tick + spec.extra_health_drain_per_tick
        pet_state.health = clamp_stat(pet_state.health - total_health_loss)

        if spec.weight_linked:
            updated.append(entry)
        elif entry.ticks_remaining is None:
            updated.append(entry)
        else:
            new_ticks = entry.ticks_remaining - 1
            if new_ticks <= 0:
                pet_state.add_event(
                    f"{pet_state.name} recovered from the {spec.display_name.lower()}.",
                    tick_time,
                )
            else:
                updated.append(ActiveIllness(entry.illness_id, new_ticks))

    pet_state.active_illnesses = updated


def create_new_pet(now: datetime, name: str, rng: Random | None = None) -> PetState:
    pet_state = PetState(
        name=name,
        character=roll_starting_character(rng),
        stage=STAGE_EGG,
        weight=5,
        hunger=100,
        happiness=100,
        health=100,
        energy=100,
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


def reconcile_state(pet_state: PetState, now: datetime, rng: Random | None = None) -> PetState:
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

    for tick_index in range(tick_count):
        tick_time = pet_state.last_tick_at + timedelta(minutes=TICK_MINUTES * (tick_index + 1))
        _apply_tick(pet_state, tick_time, rng)
        emit_plugin_event("on_tick", pet_state=pet_state, tick_time=tick_time)
        new_stage = stage_for_age(tick_time - pet_state.created_at, pet_state.is_alive)
        if new_stage != pet_state.stage:
            old_stage = pet_state.stage
            emit_plugin_event(
                "on_stage_change",
                pet_state=pet_state,
                old_stage=old_stage,
                new_stage=new_stage,
                at=tick_time,
            )
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

    if tick_count == 0:
        new_stage_idle = stage_for_age(now - pet_state.created_at, pet_state.is_alive)
        if pet_state.is_alive and new_stage_idle != pet_state.stage:
            old_stage_idle = pet_state.stage
            emit_plugin_event(
                "on_stage_change",
                pet_state=pet_state,
                old_stage=old_stage_idle,
                new_stage=new_stage_idle,
                at=now,
            )
            pet_state.stage = new_stage_idle
            pet_state.stage_started_at = now
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
        "medicine": _medicine_pet,
    }

    if normalized_action not in action_messages:
        raise ValueError(f"Unsupported action: {action}")

    message = action_messages[normalized_action](pet_state, now)
    pet_state.last_interaction_at = now
    pet_state.updated_at = now
    emit_plugin_event(
        "on_action",
        pet_state=pet_state,
        action=normalized_action,
        now=now,
    )
    return ActionResult(pet_state=pet_state, message=message)


def _apply_tick(pet_state: PetState, tick_time: datetime, rng: Random | None = None) -> None:
    if pet_state.is_asleep:
        pet_state.hunger = clamp_stat(pet_state.hunger - 1)
        pet_state.awake_minutes = 0
        if pet_state.hunger >= 30:
            pet_state.health = clamp_stat(pet_state.health + 1)
        _apply_sleep_energy_gain(pet_state)
    else:
        pet_state.hunger = clamp_stat(pet_state.hunger - 3)
        pet_state.happiness = clamp_stat(pet_state.happiness - 2)
        pet_state.awake_minutes += TICK_MINUTES
        _apply_awake_energy_drain(pet_state)

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

    _sync_weight_linked_illnesses(pet_state, tick_time)
    _process_active_illnesses(pet_state, tick_time)

    active_ids = [entry.illness_id for entry in pet_state.active_illnesses]
    if pet_state.is_alive:
        contract_chance = illness_contraction_chance(pet_state.health, active_ids)
        if contract_chance > 0:
            roll_source = rng if rng is not None else random_module
            if roll_source.random() < contract_chance:
                pick_source = rng if rng is not None else Random()
                active_set = {entry.illness_id for entry in pet_state.active_illnesses}
                contracted = pick_random_illness(pick_source, active_set)
                if contracted is not None:
                    contracted_spec = ILLNESS_DEFINITION_BY_ENUM[contracted]
                    pet_state.active_illnesses.append(
                        ActiveIllness(contracted.value, contracted_spec.duration_ticks)
                    )
                    pet_state.add_event(
                        f"{pet_state.name} fell ill ({contracted_spec.display_name.lower()}).",
                        tick_time,
                    )

    if pet_state.health == 0:
        pet_state.active_illnesses = list()
        pet_state.death_morph_stage = death_morph_for_live_stage(pet_state.stage)
        pet_state.is_alive = False
        pet_state.stage = STAGE_DEAD
        pet_state.stage_started_at = tick_time
        pet_state.graveyard_needs_entry = True
        pet_state.add_event(f"{pet_state.name} has passed away.", tick_time)
        emit_plugin_event("on_death", pet_state=pet_state, cause="health")


def _feed_pet(pet_state: PetState, now: datetime) -> str:
    if pet_state.hunger >= 100:
        pet_state.add_event(f"{pet_state.name} is not hungry.", now)
        return f"{pet_state.name} is already full."

    weight_before = pet_state.weight
    weight_min, weight_max = healthy_weight_bounds(pet_state.character)
    pet_state.hunger = clamp_stat(pet_state.hunger + 25)
    pet_state.happiness = clamp_stat(pet_state.happiness + 4)
    pet_state.weight += 1
    pet_state.add_event(f"You fed {pet_state.name}.", now)
    if weight_before <= weight_max < pet_state.weight:
        pet_state.add_event(f"{pet_state.name} is putting on weight.", now)
    sluggish_line = weight_max + SLUGGISH_WEIGHT_OFFSET
    if weight_before <= sluggish_line < pet_state.weight:
        pet_state.add_event(f"{pet_state.name} seems sluggish from the extra weight.", now)
    _sync_weight_linked_illnesses(pet_state, now)
    return f"You fed {pet_state.name}."


def _play_with_pet(pet_state: PetState, now: datetime) -> str:
    if pet_state.is_asleep:
        return f"{pet_state.name} is asleep. Turn the lights on before playing."

    energy_cost = _play_energy_cost(pet_state)
    if pet_state.energy < energy_cost:
        pet_state.add_event(f"{pet_state.name} is too exhausted to play.", now)
        return f"{pet_state.name} is too tired to play. Let them sleep to recover energy."

    pet_state.energy = clamp_stat(pet_state.energy - energy_cost)
    pet_state.happiness = clamp_stat(pet_state.happiness + 18)
    pet_state.hunger = clamp_stat(pet_state.hunger - 6)
    pet_state.health = clamp_stat(pet_state.health + 2)
    pet_state.weight = max(1, pet_state.weight - 1)

    play_penalty = 0
    for entry in pet_state.active_illnesses:
        ill = illness_from_value(entry.illness_id)
        if ill is None:
            continue
        play_penalty += ILLNESS_DEFINITION_BY_ENUM[ill].play_health_cost
    if play_penalty > 0:
        pet_state.health = clamp_stat(pet_state.health - play_penalty)

    pet_state.add_event(f"You played with {pet_state.name}.", now)
    _sync_weight_linked_illnesses(pet_state, now)
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


def _medicine_pet(pet_state: PetState, now: datetime) -> str:
    if pet_state.last_medicine_at is not None:
        elapsed = now - pet_state.last_medicine_at
        if elapsed < MEDICINE_COOLDOWN:
            remaining = MEDICINE_COOLDOWN - elapsed
            seconds_left = int(remaining.total_seconds())
            minutes_left = max(1, (seconds_left + 59) // 60)
            return f"Medicine is recharging. Try again in about {minutes_left} minute(s)."

    had_curable = False
    kept: list[ActiveIllness] = list()
    for entry in pet_state.active_illnesses:
        ill = illness_from_value(entry.illness_id)
        if ill is None:
            continue
        if ILLNESS_DEFINITION_BY_ENUM[ill].weight_linked:
            kept.append(entry)
        else:
            had_curable = True
    pet_state.active_illnesses = kept

    heal_amount = max(1, round(pet_state.health * MEDICINE_HEAL_FRACTION))
    pet_state.health = clamp_stat(pet_state.health + heal_amount)
    pet_state.last_medicine_at = now
    pet_state.add_event(f"You gave {pet_state.name} medicine.", now)
    if had_curable:
        pet_state.add_event(f"{pet_state.name} is cured and looks steadier.", now)
    return f"You gave {pet_state.name} medicine (+{heal_amount} health)."
