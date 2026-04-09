from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from cli_tamagotchi.engine import TICK_MINUTES, apply_action, create_new_pet, reconcile_state
from cli_tamagotchi.plugins.base import BasePlugin
from cli_tamagotchi.plugins.manager import PluginManager, list_plugin_entry_point_specs, plugin_manager


class ActionCountPlugin(BasePlugin):
    name = "action_counter"
    description = "test"
    version = "0.0.1"

    def __init__(self) -> None:
        self.actions = 0

    def on_action(self, pet_state, action, now):  # noqa: ANN001
        self.actions += 1


class UnloadPlugin(BasePlugin):
    name = "unload_probe"
    description = "test"
    version = "0.0.1"

    def __init__(self) -> None:
        self.unloaded = False

    def on_unload(self) -> None:
        self.unloaded = True


class HitPlugin(BasePlugin):
    def __init__(self, logical_name: str) -> None:
        super().__init__()
        self.name = logical_name
        self.hits = 0

    def on_external_event(self, event_type, data):  # noqa: ANN001
        self.hits += 1


class PluginSystemTests(TestCase):
    def setUp(self) -> None:
        self.base_time = datetime(2024, 1, 1, 12, 0, 0)
        self.temp_base = Path(tempfile.mkdtemp())
        plugin_manager.configure(self.temp_base)

    def tearDown(self) -> None:
        reset_dir = self.temp_base / "teardown_plugins"
        reset_dir.mkdir(exist_ok=True)
        plugin_manager.configure(Path.home() / ".cli-tamagotchi")
        plugin_manager.reload(user_plugin_dir=reset_dir)

    def test_user_plugin_discovered_from_directory(self) -> None:
        plugin_dir = self.temp_base / "plugins"
        plugin_dir.mkdir(parents=True)
        plugin_file = plugin_dir / "counter.py"
        plugin_file.write_text(
            """
from cli_tamagotchi.plugins.base import BasePlugin

class UserTickPlugin(BasePlugin):
    name = "user_tick"
    description = "x"
    version = "1.0.0"

    def __init__(self):
        self.n = 0

    def on_tick(self, pet_state, tick_time):
        self.n += 1
""",
            encoding="utf-8",
        )

        plugin_manager.configure(self.temp_base)
        plugin_manager.reload(user_plugin_dir=plugin_dir)

        user_plugins = [p for p in plugin_manager.plugins if p.name == "user_tick"]
        self.assertEqual(len(user_plugins), 1)
        pet = create_new_pet(self.base_time, "T")
        future = self.base_time + timedelta(minutes=TICK_MINUTES * 3)
        reconcile_state(pet, future)
        self.assertEqual(user_plugins[0].n, 3)

    def test_reload_calls_on_unload(self) -> None:
        mgr = PluginManager()
        probe = UnloadPlugin()
        mgr.register(probe)
        empty_plugins = self.temp_base / "empty"
        empty_plugins.mkdir(parents=True)
        mgr.reload(user_plugin_dir=empty_plugins)
        self.assertTrue(probe.unloaded)

    def test_emit_targets_single_plugin(self) -> None:
        mgr = PluginManager()
        alpha = HitPlugin("alpha")
        beta = HitPlugin("beta")
        mgr.register(alpha)
        mgr.register(beta)
        mgr.emit("on_external_event", target="beta", event_type="x", data={})
        self.assertEqual(alpha.hits, 0)
        self.assertEqual(beta.hits, 1)

    def test_list_plugin_entry_point_specs_returns_sorted(self) -> None:
        specs = list_plugin_entry_point_specs()
        names = [ep.name for ep in specs]
        self.assertEqual(names, sorted(names))

    def test_apply_action_emits_on_action(self) -> None:
        reset_dir = self.temp_base / "p_action_plugins"
        reset_dir.mkdir(parents=True)
        plugin_manager.configure(self.temp_base)
        plugin_manager.reload(user_plugin_dir=reset_dir)
        counter = ActionCountPlugin()
        plugin_manager.register(counter)

        pet = create_new_pet(self.base_time, "T")
        apply_action(pet, "feed", self.base_time)
        self.assertGreaterEqual(counter.actions, 1)

    def test_claude_hook_post_tool(self) -> None:
        from claude_code.plugin import build_hook_event

        old_argv = sys.argv
        try:
            sys.argv = ["tama-hook", "post-tool", "bash", "0"]
            from cli_tamagotchi.plugins.hooks import tama_hook_main

            with patch(
                "cli_tamagotchi.plugins.hooks._iter_hook_builders",
                return_value=[build_hook_event],
            ):
                tama_hook_main()
        finally:
            sys.argv = old_argv

        lines = (self.temp_base / "claude_events.jsonl").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        payload = json.loads(lines[0])
        self.assertEqual(payload["type"], "post_tool")
        self.assertEqual(payload["tool"], "bash")
