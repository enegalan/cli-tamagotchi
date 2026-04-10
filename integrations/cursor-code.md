# Tamagotchi — Cursor Integration

Feed your pet from Cursor or any workflow that can append JSON lines or call `tama-hook`.
The pet reacts when `tama` runs and processes new lines from the Cursor event file.

## What it does

- **`tama-hook cursor activity <slug>`** -> applies the matching `CodingActivity` (same slugs as the core enum: `shipping`, `looping`, `exploring`, `blocked`, `tests_passed`, `tests_failed`, `sub_agent_spawned`)
- **Raw JSONL** -> each line `{"activity":"<slug>"}` (optional `"silent": true` to skip the log line)

Cursor does not publish a single stable schema for agent transcripts across versions. You either call the hook from your own automation or append lines in that shape (for example after transforming agent output).

## Invocation

Wire `tama-hook cursor activity …` from a shell script, task, or external tool that runs when you want the pet to notice something.

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

Events land in JSONL here:

- default: `~/.cli-tamagotchi/cursor_events.jsonl`
- override: `$CLI_TAMAGOTCHI_HOME/cursor_events.jsonl`

The `cursor_code` plugin reads this file on each tick while `tama` is running.

### Step 3: Send events

Either append JSONL yourself:

```bash
printf '%s\n' '{"activity":"exploring"}' >> ~/.cli-tamagotchi/cursor_events.jsonl
```

Or use the hook (writes the same shape):

```bash
tama-hook cursor activity exploring
```

### Step 4: Verify

```bash
tama status
```

Optional debug check:

```bash
tail -n 10 ~/.cli-tamagotchi/cursor_events.jsonl
```

## Hook commands reference

| Command | When fired | Pet effect |
|---------|------------|------------|
| `tama-hook cursor activity <slug>` | You choose | Applies `CodingActivity` for `<slug>` |

## Line format (JSONL)

Each line is a JSON object:

- `activity` (string, required): must match a `CodingActivity` value
- `silent` (boolean, optional): if true, stats still update but no new event log line

## Requires

- `tama` and `tama-hook` on `$PATH`
- An existing pet (`tama`)
