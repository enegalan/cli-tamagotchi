# cli-tamagotchi

`cli-tamagotchi` is a terminal-first Tamagotchi. It gives you one persistent pet, keeps aging it while the CLI is closed, and lets you care for it with a small `tama` command set.

## Features

- **One active pet** in `~/.cli-tamagotchi/pet.json` (override the data directory with `CLI_TAMAGOTCHI_HOME`)
- **Graveyard** for past pets in `~/.cli-tamagotchi/graveyard.json`
- **Stats:** hunger, happiness, health, weight, energy, dirtiness; wake/sleep; optional illnesses
- **Life stages:** Egg → Baby → Child → Adult (time-based growth), with death when care or health fails
- **Offline decay** reconciled from elapsed real time whenever you run a command
- **Care actions:** feed, play, lights on/off, clean, medicine (one-hour cooldown; helps cure illness)
- **Event log** stored with the pet state (trimmed to the most recent entries)
- **ASCII sprites** with mood and stage-aware animation in the UI
- **CLI subcommands** for quick actions, plus **`tama` alone** for the interactive loop
- **Plugin system** with lifecycle hooks (`on_tick`, `on_event`, `on_action`, `on_external_event`, ...)

## Requirements

- Python **3.9+**

## Install and run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### CLI (`tama`)

```bash
tama status
tama feed
tama play
tama lights
tama clean
tama medicine
tama logs
tama new          # only when no living pet
tama graveyard
tama plugin emit my_event --data '{"k":"v"}'   # notify all plugins
tama              # interactive UI
```

Plugins are loaded when `tama` starts. To pick up plugin code changes, restart the command.

Setup details: [integrations/README.md](integrations/README.md).

Run without installing the console script:

```bash
PYTHONPATH=src:plugins python3 -m cli_tamagotchi status
```

Use `tama -h` for built-in help on subcommands.

## Interactive mode

Running `tama` with no arguments starts the main UI: status, animated pet, stat bars, and an action grid. On a proper TTY, navigation uses single-key input; otherwise a simple line-based fallback is used.

While your pet is alive you can use feed, play, lights, clean, medicine, open the **graveyard** view, or quit. After death you can start a **new pet** (when allowed) or browse the graveyard. The event log can be scrolled when shown in the interactive layout.

## Persistence

State lives under `~/.cli-tamagotchi/` by default (or under `CLI_TAMAGOTCHI_HOME` if set). The save includes name, character, stage, weight, stats, sleep and dirtiness, illness and medicine timestamps, timestamps for creation/updates/ticks/interactions, and the recent event log. Offline progression runs from the last processed tick when any command loads the pet.

## Tests

```bash
python3 -m pytest tests/
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
