# Tamagotchi — CI/CD Integration

Let pipeline outcomes reach your pet: green runs cheer, red runs sting, via one line per outcome in JSONL.

## What it does

- **`tama-hook ci pass`** -> `tests_passed` reaction
- **`tama-hook ci fail`** -> `tests_failed` reaction

You can append the same shape to `ci_events.jsonl` from any CI system that can run a shell step or HTTP-less sidecar.

## Invocation

Add a final step (or `after_script`) that runs `tama-hook` when the job finishes, using the job exit status to choose `pass` or `fail`.

## Workflow

### Step 1: Check prerequisites

Verify `tama` and `tama-hook` are available on the runner, and your pet exists on the machine where you run `tama` interactively (the JSONL file must be the same home, or sync it if you split environments).

```bash
tama --version
tama status
tama-hook
```

If the runner has no pet file, hooks still append lines; reactions apply the next time `tama` loads that save path.

### Step 2: Know the event file path

CI hooks append to:

- default: `~/.cli-tamagotchi/ci_events.jsonl`
- override: `$CLI_TAMAGOTCHI_HOME/ci_events.jsonl`

The `ci_cd` plugin reads this file on each tick.

### Step 3: Call from the pipeline

On success:

```bash
tama-hook ci pass
```

On failure:

```bash
tama-hook ci fail
```

Example pattern (conceptual; adapt to your CI’s syntax):

```bash
if [ "$CI_JOB_STATUS" = "success" ]; then tama-hook ci pass; else tama-hook ci fail; fi
```

### Step 4: Verify

On the machine where you use `tama`:

```bash
tama status
```

Optional debug check:

```bash
tail -n 10 ~/.cli-tamagotchi/ci_events.jsonl
```

## Hook commands reference

| Command | When fired | Pet effect |
|---------|------------|------------|
| `tama-hook ci pass` | Pipeline / job succeeded | `tests_passed` |
| `tama-hook ci fail` | Pipeline / job failed | `tests_failed` |

## Line format (JSONL)

Hooks write `{"activity":"<slug>","ts":...}`. Valid slugs for manual use are the same as `CodingActivity` in the core package.

## Requires

- `tama` and `tama-hook` available where hooks run (or equivalent append to the JSONL path)
- An existing pet when you want to see reactions in `tama`
