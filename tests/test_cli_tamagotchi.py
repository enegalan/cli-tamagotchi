from __future__ import annotations

import io
import random
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from random import Random
from unittest.mock import patch

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from cli_tamagotchi.cli import (
    NO_ACTION,
    _clamp_selection,
    _default_event_offset,
    build_action_grid,
    name_from_flag_or_prompt,
    _move_event_offset,
    _move_selection,
    _normalize_action_input,
    _read_action_input,
    _read_single_key,
    main,
)
from cli_tamagotchi.characters import roll_starting_character
from cli_tamagotchi.engine import TICK_MINUTES, apply_action, create_new_pet, reconcile_state
from cli_tamagotchi.illnesses import Illness
from cli_tamagotchi.models import ActiveIllness, REACTION_ANIMATION_WINDOW, STAGE_BABY, STAGE_DEAD
from cli_tamagotchi.render import render_status
from cli_tamagotchi.sprites import FRAME_INTERVAL_MS, get_sprite_lines
from cli_tamagotchi.storage import PetStorage


class ZeroRandom(Random):
    def random(self) -> float:
        return 0.0


class TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


class CliTamagotchiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.storage = PetStorage(base_dir=Path(self.temporary_directory.name))
        self.base_time = datetime(2026, 4, 8, 12, 0, 0)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @patch("cli_tamagotchi.engine.roll_starting_character", return_value="Cat")
    def test_status_command_creates_and_persists_pet(self, _mock_roll: object) -> None:
        stdout = io.StringIO()

        exit_code = main(
            argv=["--name", "Nova", "status"],
            storage=self.storage,
            now_provider=lambda: self.base_time,
            output=stdout,
            input_stream=io.StringIO(""),
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(self.storage.exists())
        persisted_pet = self.storage.load()
        self.assertIsNotNone(persisted_pet)
        assert persisted_pet is not None
        self.assertEqual(persisted_pet.name, "Nova")
        self.assertEqual(persisted_pet.character, "Cat")
        self.assertEqual(persisted_pet.weight, 5)
        self.assertIn("Nova", stdout.getvalue())
        self.assertIn("Stage", stdout.getvalue())
        self.assertIn("Character", stdout.getvalue())

    @patch("cli_tamagotchi.cli.pick_random_pet_name", return_value="Qubit")
    @patch("cli_tamagotchi.engine.roll_starting_character", return_value="Cat")
    def test_status_without_name_uses_random_default(
        self, _mock_roll: object, _mock_pick: object
    ) -> None:
        stdout = io.StringIO()
        exit_code = main(
            argv=["status"],
            storage=self.storage,
            now_provider=lambda: self.base_time,
            output=stdout,
            input_stream=io.StringIO(""),
        )
        self.assertEqual(exit_code, 0)
        persisted_pet = self.storage.load()
        self.assertIsNotNone(persisted_pet)
        assert persisted_pet is not None
        self.assertEqual(persisted_pet.name, "Qubit")

    def test_offline_reconcile_advances_stage_and_reduces_stats(self) -> None:
        pet_state = create_new_pet(self.base_time, name="Nova")
        pet_state.created_at = self.base_time - timedelta(hours=13)
        tick_gap = timedelta(minutes=26 * TICK_MINUTES)
        pet_state.last_tick_at = self.base_time - tick_gap

        reconcile_state(pet_state, self.base_time)

        self.assertEqual(pet_state.stage, STAGE_BABY)
        self.assertLess(pet_state.hunger, 80)
        self.assertLess(pet_state.happiness, 75)
        self.assertGreaterEqual(pet_state.dirtiness, 1)

    def test_sleep_slows_decay(self) -> None:
        awake_pet = create_new_pet(self.base_time, name="Nova")
        asleep_pet = create_new_pet(self.base_time, name="Nova")
        asleep_pet.is_asleep = True

        future_time = self.base_time + timedelta(minutes=TICK_MINUTES * 4)
        reconcile_state(awake_pet, future_time)
        reconcile_state(asleep_pet, future_time)

        self.assertLess(awake_pet.hunger, asleep_pet.hunger)

    def test_clean_action_resets_dirtiness(self) -> None:
        pet_state = create_new_pet(self.base_time, name="Nova")
        pet_state.dirtiness = 3
        pet_state.health = 70

        result = apply_action(pet_state, "clean", self.base_time)

        self.assertEqual(result.pet_state.dirtiness, 0)
        self.assertGreater(result.pet_state.health, 70)
        self.assertIn("cleaned", result.message.lower())

    def test_feed_increases_weight(self) -> None:
        pet_state = create_new_pet(self.base_time, name="Nova")
        pet_state.hunger = 80

        result = apply_action(pet_state, "feed", self.base_time)

        self.assertEqual(result.pet_state.weight, 6)

    def test_feed_when_hunger_full_does_nothing(self) -> None:
        pet_state = create_new_pet(self.base_time, name="Nova")
        pet_state.hunger = 100
        weight_before = pet_state.weight

        result = apply_action(pet_state, "feed", self.base_time)

        self.assertEqual(result.pet_state.weight, weight_before)
        self.assertEqual(result.pet_state.hunger, 100)
        self.assertIn("full", result.message.lower())
        self.assertTrue(any("not hungry" in entry.message.lower() for entry in pet_state.events))

    def test_overweight_tick_extra_happiness_decay(self) -> None:
        heavy = create_new_pet(self.base_time, name="Heavy")
        heavy.character = "Cat"
        heavy.weight = 28
        thin = create_new_pet(self.base_time, name="Thin")
        thin.character = "Cat"
        heavy.last_tick_at = self.base_time - timedelta(minutes=TICK_MINUTES)
        thin.last_tick_at = self.base_time - timedelta(minutes=TICK_MINUTES)

        reconcile_state(heavy, self.base_time)
        reconcile_state(thin, self.base_time)

        self.assertLess(heavy.happiness, thin.happiness)

    def test_obese_tick_hurts_health_more_than_overweight(self) -> None:
        obese = create_new_pet(self.base_time, name="Obese")
        obese.character = "Cat"
        obese.weight = 35
        overweight = create_new_pet(self.base_time, name="Over")
        overweight.character = "Cat"
        overweight.weight = 25
        obese.last_tick_at = self.base_time - timedelta(minutes=TICK_MINUTES)
        overweight.last_tick_at = self.base_time - timedelta(minutes=TICK_MINUTES)

        reconcile_state(obese, self.base_time)
        reconcile_state(overweight, self.base_time)

        self.assertLess(obese.health, overweight.health)

    def test_obese_penalties_skip_while_asleep(self) -> None:
        obese_awake = create_new_pet(self.base_time, name="A")
        obese_awake.character = "Cat"
        obese_awake.weight = 40
        obese_asleep = create_new_pet(self.base_time, name="B")
        obese_asleep.character = "Cat"
        obese_asleep.weight = 40
        obese_asleep.is_asleep = True
        obese_awake.last_tick_at = self.base_time - timedelta(minutes=TICK_MINUTES)
        obese_asleep.last_tick_at = self.base_time - timedelta(minutes=TICK_MINUTES)

        reconcile_state(obese_awake, self.base_time)
        reconcile_state(obese_asleep, self.base_time)

        self.assertLess(obese_awake.happiness, obese_asleep.happiness)

    def test_feed_warns_when_crossing_into_overweight(self) -> None:
        pet_state = create_new_pet(self.base_time, name="Nova")
        pet_state.character = "Cat"
        pet_state.weight = 26
        pet_state.hunger = 80

        apply_action(pet_state, "feed", self.base_time)

        self.assertTrue(
            any("putting on weight" in entry.message.lower() for entry in pet_state.events)
        )

    def test_low_health_tick_can_contract_illness(self) -> None:
        pet_state = create_new_pet(self.base_time, name="Nova")
        pet_state.health = 10
        pet_state.last_tick_at = self.base_time - timedelta(minutes=TICK_MINUTES)

        reconcile_state(pet_state, self.base_time, rng=ZeroRandom())

        timed = [
            entry
            for entry in pet_state.active_illnesses
            if entry.ticks_remaining is not None
        ]
        self.assertTrue(len(timed) >= 1)
        self.assertGreater(timed[0].ticks_remaining or 0, 0)

    def test_high_health_no_random_illness_contract(self) -> None:
        pet_state = create_new_pet(self.base_time, name="Nova")
        pet_state.health = 90
        pet_state.last_tick_at = self.base_time - timedelta(minutes=TICK_MINUTES)

        reconcile_state(pet_state, self.base_time, rng=ZeroRandom())

        self.assertEqual(len(pet_state.active_illnesses), 0)

    def test_illness_tick_drains_and_can_expire(self) -> None:
        pet_state = create_new_pet(self.base_time, name="Nova")
        pet_state.health = 60
        pet_state.hunger = 60
        pet_state.happiness = 60
        pet_state.active_illnesses = [ActiveIllness(Illness.SNIFFLES.value, 1)]
        pet_state.last_tick_at = self.base_time - timedelta(minutes=TICK_MINUTES)

        reconcile_state(pet_state, self.base_time)

        self.assertEqual(len(pet_state.active_illnesses), 0)
        self.assertEqual(pet_state.happiness, 57)
        self.assertTrue(any("recovered" in entry.message.lower() for entry in pet_state.events))

    def test_medicine_cures_illness_and_heals(self) -> None:
        pet_state = create_new_pet(self.base_time, name="Nova")
        pet_state.active_illnesses = [ActiveIllness(Illness.COLD.value, 6)]
        pet_state.health = 40

        result = apply_action(pet_state, "medicine", self.base_time)

        self.assertFalse(result.pet_state.has_illness_id(Illness.COLD.value))
        self.assertGreater(result.pet_state.health, 40)
        self.assertIn("medicine", result.message.lower())

    def test_medicine_clears_only_non_weight_illnesses(self) -> None:
        pet_state = create_new_pet(self.base_time, name="Nova")
        pet_state.weight = 2
        pet_state.active_illnesses = [
            ActiveIllness(Illness.UNDERWEIGHT.value, None),
            ActiveIllness(Illness.FEVER.value, 4),
        ]
        pet_state.health = 50

        result = apply_action(pet_state, "medicine", self.base_time)

        self.assertTrue(result.pet_state.has_illness_id(Illness.UNDERWEIGHT.value))
        self.assertFalse(result.pet_state.has_illness_id(Illness.FEVER.value))

    def test_play_blocked_without_energy(self) -> None:
        pet_state = create_new_pet(self.base_time, name="Nova")
        pet_state.energy = 0

        result = apply_action(pet_state, "play", self.base_time)

        self.assertIn("tired", result.message.lower())

    def test_sleep_tick_restores_energy(self) -> None:
        pet_state = create_new_pet(self.base_time, name="Nova")
        pet_state.is_asleep = True
        pet_state.energy = 30
        pet_state.last_tick_at = self.base_time - timedelta(minutes=TICK_MINUTES)

        reconcile_state(pet_state, self.base_time)

        self.assertGreater(pet_state.energy, 30)

    @patch("cli_tamagotchi.engine.TICK_MINUTES", 30)
    def test_medicine_hour_cooldown(self) -> None:
        pet_state = create_new_pet(self.base_time, name="Nova")

        first = apply_action(pet_state, "medicine", self.base_time)
        self.assertIn("medicine", first.message.lower())

        second = apply_action(pet_state, "medicine", self.base_time + timedelta(minutes=30))
        self.assertIn("recharging", second.message.lower())

        third = apply_action(pet_state, "medicine", self.base_time + timedelta(hours=1, seconds=1))
        self.assertIn("medicine", third.message.lower())

    def test_feed_warns_when_crossing_into_obese(self) -> None:
        pet_state = create_new_pet(self.base_time, name="Nova")
        pet_state.character = "Cat"
        pet_state.weight = 32
        pet_state.hunger = 80

        apply_action(pet_state, "feed", self.base_time)

        self.assertTrue(
            any("sluggish" in entry.message.lower() for entry in pet_state.events)
        )

    def test_lights_toggle_sleep_state(self) -> None:
        pet_state = create_new_pet(self.base_time, name="Nova")

        lights_off_result = apply_action(pet_state, "lights", self.base_time)
        self.assertTrue(lights_off_result.pet_state.is_asleep)
        self.assertIn("lights off", lights_off_result.message.lower())

        lights_on_result = apply_action(pet_state, "lights", self.base_time)
        self.assertFalse(lights_on_result.pet_state.is_asleep)
        self.assertIn("lights on", lights_on_result.message.lower())

    def test_interactive_loop_accepts_action_then_quit(self) -> None:
        stdout = io.StringIO()
        stdin = io.StringIO("feed\nquit\n")
        pet_state = create_new_pet(self.base_time, name="Loop")
        pet_state.hunger = 80
        self.storage.save(pet_state)

        exit_code = main(
            argv=["--name", "Loop"],
            storage=self.storage,
            now_provider=lambda: self.base_time,
            output=stdout,
            input_stream=stdin,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("You fed Loop.", stdout.getvalue())
        self.assertIn("Goodbye.", stdout.getvalue())

    def test_name_from_flag_or_prompt_reads_tty_line(self) -> None:
        out = io.StringIO()
        stdin = TtyStringIO("Pip\n")
        self.assertEqual(name_from_flag_or_prompt(None, out, stdin), "Pip")
        self.assertIn("Pet name", out.getvalue())

    @patch("cli_tamagotchi.cli.pick_random_pet_name", return_value="Zed")
    def test_name_from_flag_or_prompt_empty_line_uses_random(self, _mock: object) -> None:
        stdin = TtyStringIO("\n")
        self.assertEqual(name_from_flag_or_prompt(None, io.StringIO(), stdin), "Zed")

    def test_name_from_flag_skips_prompt(self) -> None:
        out = io.StringIO()
        stdin = TtyStringIO("ignored\n")
        self.assertEqual(name_from_flag_or_prompt("Ada", out, stdin), "Ada")
        self.assertEqual(out.getvalue(), "")

    def test_normalize_action_input_supports_commands(self) -> None:
        self.assertEqual(_normalize_action_input("play"), "play")
        self.assertEqual(_normalize_action_input("lights"), "lights")
        self.assertEqual(_normalize_action_input("medicine"), "medicine")
        self.assertIsNone(_normalize_action_input("status"))
        self.assertEqual(_normalize_action_input("quit"), "quit")
        self.assertEqual(_normalize_action_input("new"), "new_pet")
        self.assertEqual(_normalize_action_input("new pet"), "new_pet")
        self.assertEqual(_normalize_action_input("pgup"), "events_up")
        self.assertEqual(_normalize_action_input("pagedown"), "events_down")
        self.assertIsNone(_normalize_action_input(""))
        self.assertIsNone(_normalize_action_input("f"))

    def test_move_selection_handles_grid_navigation(self) -> None:
        alive_grid = (
            ("feed", "play"),
            ("lights_off", "clean"),
            ("medicine", "quit"),
        )
        self.assertEqual(_move_selection(alive_grid, (0, 0), "right"), (0, 1))
        self.assertEqual(_move_selection(alive_grid, (0, 1), "down"), (1, 1))
        self.assertEqual(_move_selection(alive_grid, (1, 1), "down"), (2, 1))
        self.assertEqual(_move_selection(alive_grid, (2, 1), "left"), (2, 0))
        self.assertEqual(_move_selection(alive_grid, (2, 0), "up"), (1, 0))
        self.assertEqual(_move_selection(alive_grid, (2, 1), "down"), (2, 1))

    def test_clamp_selection_snaps_to_filled_column(self) -> None:
        quit_only_grid = (("quit", None),)
        self.assertEqual(_clamp_selection(quit_only_grid, (0, 1)), (0, 0))
        self.assertEqual(_clamp_selection(quit_only_grid, (0, 0)), (0, 0))

    def test_build_action_grid_dead_includes_new_pet_when_allowed(self) -> None:
        pet_state = create_new_pet(self.base_time, name="Gone")
        pet_state.health = 0
        pet_state.is_alive = False
        pet_state.stage = STAGE_DEAD
        grid = build_action_grid(pet_state, self.storage)
        self.assertEqual(
            grid,
            (("new_pet", "quit"),),
        )

    def test_cli_new_command_rejects_when_pet_alive(self) -> None:
        stdout = io.StringIO()
        exit_code = main(
            argv=["--name", "X", "new"],
            storage=self.storage,
            now_provider=lambda: self.base_time,
            output=stdout,
            input_stream=io.StringIO(),
        )
        self.assertEqual(exit_code, 1)
        self.assertIn("already alive", stdout.getvalue().lower())

    def test_event_offset_moves_within_bounds(self) -> None:
        pet_state = create_new_pet(self.base_time, name="Nova")
        for index in range(10):
            pet_state.add_event(f"Event {index}", self.base_time + timedelta(minutes=index))

        event_offset = _default_event_offset(pet_state, 6)
        self.assertEqual(event_offset, 5)
        self.assertEqual(_move_event_offset(pet_state, event_offset, 6, -2), 3)
        self.assertEqual(_move_event_offset(pet_state, 0, 6, -1), 0)
        self.assertEqual(_move_event_offset(pet_state, 5, 6, 10), 5)

    def test_render_status_shows_events_panel_and_range(self) -> None:
        pet_state = create_new_pet(self.base_time, name="Nova")
        for index in range(8):
            pet_state.add_event(f"Event {index}", self.base_time + timedelta(minutes=index))

        rendered_status = render_status(pet_state, event_offset=2, event_limit=4)

        self.assertEqual(getattr(rendered_status, "renderables")[1].title, "Events")
        self.assertEqual(getattr(rendered_status, "renderables")[1].subtitle, "3-6 of 9 | PgUp/PgDn scroll")

    def test_get_sprite_lines_returns_sleeping_variant_when_asleep(self) -> None:
        sleeping_lines = get_sprite_lines("Cat", "Baby", "happy", is_asleep=True)
        awake_lines = get_sprite_lines("Cat", "Baby", "happy", is_asleep=False)

        self.assertNotEqual(sleeping_lines, awake_lines)

    def test_get_sprite_lines_animation_time_none_is_deterministic(self) -> None:
        first_lines = get_sprite_lines("Cat", "Baby", "happy", is_asleep=False, animation_time=None)
        second_lines = get_sprite_lines("Cat", "Baby", "happy", is_asleep=False, animation_time=None)
        self.assertEqual(first_lines, second_lines)

    def test_get_sprite_lines_two_animation_times_can_differ(self) -> None:
        base = datetime(2020, 1, 1, 12, 0, 0)
        t0 = base
        t1 = base + timedelta(milliseconds=FRAME_INTERVAL_MS)
        lines_a = get_sprite_lines("Cat", "Baby", "happy", is_asleep=False, animation_time=t0)
        lines_b = get_sprite_lines("Cat", "Baby", "happy", is_asleep=False, animation_time=t1)
        self.assertNotEqual(lines_a, lines_b)

    def test_reaction_pose_id_matches_recent_feed_play_clean(self) -> None:
        pet_state = create_new_pet(self.base_time, name="T")
        pet_state.add_event("You fed T.", self.base_time)
        self.assertEqual(pet_state.reaction_pose_id(self.base_time + timedelta(seconds=1)), "eating")
        pet_state.events.clear()
        pet_state.add_event("You played with T.", self.base_time)
        self.assertEqual(pet_state.reaction_pose_id(self.base_time + timedelta(seconds=1)), "playing")
        pet_state.events.clear()
        pet_state.add_event("You cleaned T's space.", self.base_time)
        self.assertEqual(pet_state.reaction_pose_id(self.base_time + timedelta(seconds=1)), "cleaning")

    def test_reaction_pose_id_expires_after_window(self) -> None:
        pet_state = create_new_pet(self.base_time, name="T")
        pet_state.add_event("You fed T.", self.base_time)
        late = self.base_time + REACTION_ANIMATION_WINDOW + timedelta(seconds=0.5)
        self.assertIsNone(pet_state.reaction_pose_id(late))

    def test_reaction_pose_id_none_while_asleep(self) -> None:
        pet_state = create_new_pet(self.base_time, name="T")
        pet_state.is_asleep = True
        pet_state.add_event("You fed T.", self.base_time)
        self.assertIsNone(pet_state.reaction_pose_id(self.base_time + timedelta(seconds=1)))

    def test_eating_sprite_differs_from_idle(self) -> None:
        now = datetime(2020, 1, 1, 12, 0, 0)
        idle = get_sprite_lines("Cat", "Egg", "happy", is_asleep=False, animation_time=now)
        eating = get_sprite_lines(
            "Cat",
            "Egg",
            "happy",
            is_asleep=False,
            reaction_pose="eating",
            animation_time=now,
        )
        self.assertNotEqual(idle, eating)

    def test_roll_starting_character_deterministic_by_seed(self) -> None:
        self.assertEqual(roll_starting_character(random.Random(42)), "Cat")
        self.assertEqual(roll_starting_character(random.Random(0)), "Fox")

    def test_read_single_key_esc_is_ignored_when_no_follow_up_sequence(self) -> None:
        keyboard_input = io.StringIO()
        keyboard_input.fileno = lambda: 0  # type: ignore[attr-defined]
        with patch("cli_tamagotchi.cli.termios.tcgetattr", return_value=object()), patch(
            "cli_tamagotchi.cli.termios.tcsetattr"
        ), patch("cli_tamagotchi.cli.tty.setraw"), patch(
            "cli_tamagotchi.cli.os.read", return_value=b"\x1b"
        ), patch(
            "cli_tamagotchi.cli.select.select", side_effect=[([], [], [])]
        ):
            self.assertIsNone(_read_single_key(keyboard_input))

    def test_read_single_key_arrow_up_returns_up(self) -> None:
        keyboard_input = io.StringIO()
        keyboard_input.fileno = lambda: 0  # type: ignore[attr-defined]
        with patch("cli_tamagotchi.cli.termios.tcgetattr", return_value=object()), patch(
            "cli_tamagotchi.cli.termios.tcsetattr"
        ), patch("cli_tamagotchi.cli.tty.setraw"), patch(
            "cli_tamagotchi.cli.os.read", side_effect=[b"\x1b", b"[", b"A"]
        ), patch(
            "cli_tamagotchi.cli.select.select", side_effect=[([0], [], []), ([0], [], [])]
        ):
            self.assertEqual(_read_single_key(keyboard_input), "up")

    def test_read_single_key_ss3_arrow_up_returns_up(self) -> None:
        keyboard_input = io.StringIO()
        keyboard_input.fileno = lambda: 0  # type: ignore[attr-defined]
        with patch("cli_tamagotchi.cli.termios.tcgetattr", return_value=object()), patch(
            "cli_tamagotchi.cli.termios.tcsetattr"
        ), patch("cli_tamagotchi.cli.tty.setraw"), patch(
            "cli_tamagotchi.cli.os.read", side_effect=[b"\x1b", b"O", b"A"]
        ), patch(
            "cli_tamagotchi.cli.select.select", side_effect=[([0], [], []), ([0], [], [])]
        ):
            self.assertEqual(_read_single_key(keyboard_input), "up")

    def test_read_action_input_returns_no_action_for_ignored_single_key(self) -> None:
        with patch("cli_tamagotchi.cli._supports_single_key_input", return_value=True), patch(
            "cli_tamagotchi.cli._read_single_key", return_value=None
        ):
            self.assertEqual(_read_action_input(io.StringIO(), io.StringIO()), NO_ACTION)

    def test_read_action_input_idle_timeout_returns_no_action(self) -> None:
        keyboard_input = io.StringIO()
        keyboard_input.fileno = lambda: 0  # type: ignore[attr-defined]
        with patch("cli_tamagotchi.cli._supports_single_key_input", return_value=True), patch(
            "cli_tamagotchi.cli.select.select", return_value=([], [], [])
        ), patch("cli_tamagotchi.cli.termios.tcgetattr", return_value=object()), patch(
            "cli_tamagotchi.cli.termios.tcsetattr"
        ), patch("cli_tamagotchi.cli.tty.setraw"):
            self.assertEqual(
                _read_action_input(io.StringIO(), keyboard_input, idle_timeout_seconds=0.3),
                NO_ACTION,
            )
if __name__ == "__main__":
    unittest.main()
