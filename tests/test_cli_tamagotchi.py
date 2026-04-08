from __future__ import annotations

import io
import random
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from cli_tamagotchi.cli import (
    NO_ACTION,
    _default_event_offset,
    _move_event_offset,
    _move_selection,
    _normalize_action_input,
    _read_action_input,
    _read_single_key,
    main,
)
from cli_tamagotchi.characters import roll_starting_character
from cli_tamagotchi.engine import TICK_MINUTES, apply_action, create_new_pet, reconcile_state
from cli_tamagotchi.models import STAGE_BABY
from cli_tamagotchi.render import render_status
from cli_tamagotchi.sprites import get_sprite_lines
from cli_tamagotchi.storage import PetStorage


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

    def test_offline_reconcile_advances_stage_and_reduces_stats(self) -> None:
        pet_state = create_new_pet(self.base_time, name="Nova")
        pet_state.last_tick_at = self.base_time - timedelta(hours=13)
        pet_state.created_at = self.base_time - timedelta(hours=13)

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
        self.assertLess(awake_pet.health, asleep_pet.health)

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

        result = apply_action(pet_state, "feed", self.base_time)

        self.assertEqual(result.pet_state.weight, 6)

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

    def test_normalize_action_input_supports_commands(self) -> None:
        self.assertEqual(_normalize_action_input("play"), "play")
        self.assertEqual(_normalize_action_input("lights"), "lights")
        self.assertEqual(_normalize_action_input("status"), "status")
        self.assertEqual(_normalize_action_input("quit"), "quit")
        self.assertEqual(_normalize_action_input("pgup"), "events_up")
        self.assertEqual(_normalize_action_input("pagedown"), "events_down")
        self.assertEqual(_normalize_action_input(""), "status")
        self.assertIsNone(_normalize_action_input("f"))

    def test_move_selection_handles_grid_navigation(self) -> None:
        self.assertEqual(_move_selection((0, 0), "right"), (0, 1))
        self.assertEqual(_move_selection((0, 1), "down"), (1, 1))
        self.assertEqual(_move_selection((1, 1), "down"), (2, 1))
        self.assertEqual(_move_selection((2, 1), "right"), (2, 1))

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
if __name__ == "__main__":
    unittest.main()
