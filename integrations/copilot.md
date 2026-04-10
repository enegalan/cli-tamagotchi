# Tamagotchi — GitHub Copilot Integration

Copilot does not ship a Tamagotchi hook. This integration is a thin bridge: you ping the pet when you decide a completion mattered, or you append JSONL yourself.

## What it does

- **`tama-hook copilot completion`** -> `exploring` reaction (light signal that you used an assist)
- **Manual JSONL** -> append `{"activity":"exploring"}` (or any valid `activity`) to `copilot_events.jsonl`

## Invocation

Run `tama-hook copilot completion` from an editor script, macro, or external watcher you maintain. There is no built-in monitor inside this package.

## Workflow

### Step 1: Check prerequisites

Verify `tama` and `tama-hook` are available, and your pet exists:

```bash
tama --version
tama status
tama-hook
```

If missing, install the package and open `tama` once to hatch a pet.

### Step 2: Know the event file path

Events go to:

- default: `~/.cli-tamagotchi/copilot_events.jsonl`
- override: `$CLI_TAMAGOTCHI_HOME/copilot_events.jsonl`

The `copilot` plugin reads this file on each tick.

### Step 3: Wire your editor or script

Call the hook when you want a ping (example: after accepting a completion, if your editor can run a command):

```bash
tama-hook copilot completion
```

Or append a line without the hook:

```bash
printf '%s\n' '{"activity":"exploring"}' >> ~/.cli-tamagotchi/copilot_events.jsonl
```

### Step 4: Verify

```bash
tama status
```

Optional debug check:

```bash
tail -n 10 ~/.cli-tamagotchi/copilot_events.jsonl
```

## Hook commands reference

| Command | When fired | Pet effect |
|---------|------------|------------|
| `tama-hook copilot completion` | You run it from your tooling | `exploring` |

## Line format (JSONL)

Same as other tool feeds: `activity` plus optional `silent`.

## Requires

- `tama` and `tama-hook` on `$PATH`
- Your own automation if you want completion-linked pings
- An existing pet (`tama`)
