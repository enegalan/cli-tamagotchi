from __future__ import annotations

import importlib.metadata
import json
import sys
from pathlib import Path
from typing import Any, Callable, Optional, Tuple


def _append_event(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":")) + "\n")


HookBuilder = Callable[[list[str]], Optional[Tuple[Path, dict[str, object]]]]


def _iter_hook_builders() -> list[HookBuilder]:
    eps_obj = importlib.metadata.entry_points()
    if hasattr(eps_obj, "select"):
        eps = eps_obj.select(group="cli_tamagotchi.hook_builders")
    else:
        eps = eps_obj.get("cli_tamagotchi.hook_builders", tuple())
    builders: list[HookBuilder] = []
    for ep in sorted(eps, key=lambda e: e.name):
        try:
            loaded = ep.load()
            if callable(loaded):
                builders.append(loaded)
        except Exception as exc:
            print(f"[tama-hook] Failed to load {ep.name}: {exc}", file=sys.stderr)
    return builders


def tama_hook_main() -> None:
    args = sys.argv[1:]
    if not args:
        return
    for build in _iter_hook_builders():
        try:
            event: Any = build(args)
        except Exception as exc:
            print(f"[tama-hook] Error in {getattr(build, '__name__', build)!r}: {exc}", file=sys.stderr)
            continue
        if event is not None:
            path, payload = event
            _append_event(path, payload)
            return
