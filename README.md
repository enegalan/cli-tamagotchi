# cli-tamagotchi

`cli-tamagotchi` is a terminal-first Tamagotchi. It gives you one persistent pet, keeps aging it while the CLI is closed, and lets you care for it with a small `tama` command set.

## MVP Features

- One pet stored locally in `~/.cli-tamagotchi/pet.json`
- Core stats: Hunger, Happiness, Health, Weight
- Pet metadata shown in the UI: Character, Stage, and Stage Age
- Offline decay based on elapsed real time
- Four care actions: `feed`, `play`, `lights`, `clean`
- Life stages: `Egg`, `Baby`, `Child`, `Adult`
- Event log stored with the pet state
- Terminal UI rendered with `rich`
- Two ways to interact:
  - Direct subcommands for quick actions
  - A minimal interactive loop with `tama`

## Requirements

- Python `3.9+`

## Run Locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

After installation, use the CLI:

```bash
tama status
tama feed
tama play
tama lights
tama clean
tama
```

You can also run it without installing the console script:

```bash
PYTHONPATH=src python3 -m cli_tamagotchi status
```

## Interactive Mode

Run `tama` with no subcommand to open the lightweight terminal loop. The UI supports:

- `feed`
- `play`
- `lights`
- `clean`
- `status`
- `quit`

## Persistence Model

The pet is stored as JSON under `~/.cli-tamagotchi/`. The saved state includes:

- Current stage
- Current character
- Current weight
- Current stats
- Sleep state and stage start timestamp
- Dirtiness and awake time
- Creation, update, interaction, and tick timestamps
- Recent event log

Offline progression is reconciled from the last processed tick whenever you run a command.

## Tests

```bash
python3 -m unittest discover -s tests
```
