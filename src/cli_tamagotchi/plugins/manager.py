from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import BasePlugin


def _log_plugin_error(plugin: BasePlugin, event: str, exc: BaseException) -> None:
    detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
    print(f"[plugin:{plugin.name}] Error in {event}: {detail}", file=sys.stderr)


@dataclass(frozen=True)
class PluginMeta:
    kind: str
    entry_name: str | None = None
    path: str | None = None
    distribution: str | None = None


class PluginManager:
    def __init__(self) -> None:
        self._plugins: list[BasePlugin] = list()
        self._plugin_meta: dict[int, PluginMeta] = {}
        self._data_home: Path | None = None

    def configure(self, data_home: Path) -> None:
        self._data_home = data_home

    @property
    def data_home(self) -> Path:
        if self._data_home is None:
            custom_home = os.environ.get("CLI_TAMAGOTCHI_HOME")
            if custom_home:
                return Path(custom_home).expanduser()
            return Path.home() / ".cli-tamagotchi"
        return self._data_home

    def meta_for(self, plugin: BasePlugin) -> PluginMeta | None:
        return self._plugin_meta.get(id(plugin))

    def discover(self, user_plugin_dir: Path | None = None) -> None:
        self._plugins.clear()
        self._plugin_meta.clear()
        self._load_entry_point_plugins()
        plugin_dir = user_plugin_dir if user_plugin_dir is not None else self.data_home / "plugins"
        self._load_user_plugins(plugin_dir)

    def _dist_name_for_entry(self, ep: importlib.metadata.EntryPoint) -> str | None:
        dist = getattr(ep, "dist", None)
        if dist is None:
            return None
        try:
            return dist.metadata["Name"]
        except Exception:
            return None

    def _attach_plugin(self, plugin: BasePlugin, meta: PluginMeta) -> None:
        self._plugins.append(plugin)
        self._plugin_meta[id(plugin)] = meta
        plugin.on_load()

    def _load_entry_point_plugins(self) -> None:
        eps_obj = importlib.metadata.entry_points()
        if hasattr(eps_obj, "select"):
            eps = eps_obj.select(group="cli_tamagotchi.plugins")
        else:
            eps = eps_obj.get("cli_tamagotchi.plugins", tuple())
        for ep in eps:
            try:
                cls = ep.load()
                plugin = cls()
                if not isinstance(plugin, BasePlugin):
                    continue
                meta = PluginMeta(
                    kind="entry_point",
                    entry_name=ep.name,
                    distribution=self._dist_name_for_entry(ep),
                )
                self._attach_plugin(plugin, meta)
            except Exception as exc:
                print(f"[plugin] Failed to load entry point {ep.name}: {exc}", file=sys.stderr)

    def _load_user_plugins(self, plugin_dir: Path) -> None:
        if not plugin_dir.is_dir():
            return
        for py_file in sorted(plugin_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                module_name = f"_cli_tamagotchi_user_plugin_{py_file.stem}"
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec is None or spec.loader is None:
                    continue
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                for attr_name in dir(mod):
                    obj = getattr(mod, attr_name)
                    if (
                        isinstance(obj, type)
                        and issubclass(obj, BasePlugin)
                        and obj is not BasePlugin
                    ):
                        plugin = obj()
                        meta = PluginMeta(kind="user_file", path=str(py_file.resolve()))
                        self._attach_plugin(plugin, meta)
            except Exception as exc:
                print(f"[plugin] Failed to load {py_file.name}: {exc}", file=sys.stderr)

    def register(self, plugin: BasePlugin) -> None:
        self._attach_plugin(plugin, PluginMeta(kind="manual"))

    def reload(self, user_plugin_dir: Path | None = None) -> None:
        for plugin in self._plugins:
            try:
                plugin.on_unload()
            except Exception as exc:
                _log_plugin_error(plugin, "on_unload", exc)
        self._plugins.clear()
        self._plugin_meta.clear()
        self.discover(user_plugin_dir=user_plugin_dir)

    def _plugin_matches_target(self, plugin: BasePlugin, target: str) -> bool:
        needle = target.strip().lower()
        if plugin.name.lower() == needle:
            return True
        meta = self._plugin_meta.get(id(plugin))
        if meta and meta.entry_name and meta.entry_name.lower() == needle:
            return True
        return False

    def plugins_matching(self, target: str) -> list[BasePlugin]:
        return [p for p in self._plugins if self._plugin_matches_target(p, target)]

    def emit(self, event: str, *, target: str | None = None, **kwargs: Any) -> None:
        for plugin in self._plugins:
            if target is not None and not self._plugin_matches_target(plugin, target):
                continue
            handler = getattr(plugin, event, None)
            if not callable(handler):
                continue
            try:
                handler(**kwargs)
            except Exception as exc:
                _log_plugin_error(plugin, event, exc)

    @property
    def plugins(self) -> list[BasePlugin]:
        return list(self._plugins)


# PyPI
DISTRIBUTION_PIP_SPEC = "cli-tamagotchi"


def list_plugin_entry_point_specs(group: str = "cli_tamagotchi.plugins") -> list[importlib.metadata.EntryPoint]:
    eps_obj = importlib.metadata.entry_points()
    if hasattr(eps_obj, "select"):
        eps = eps_obj.select(group=group)
    else:
        eps = eps_obj.get(group, tuple())
    return sorted(eps, key=lambda e: e.name)


plugin_manager = PluginManager()


def emit_plugin_event(event: str, **kwargs: Any) -> None:
    try:
        plugin_manager.emit(event, **kwargs)
    except Exception:
        pass


def get_plugin_data_home() -> Path:
    return plugin_manager.data_home
