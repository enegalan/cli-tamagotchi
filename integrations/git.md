# Tamagotchi — Git Integration

Connect Git to your pet so commits, merges, and rebases nudge stats through `tama-hook`.
Hooks append one JSON line per invocation; the `git_tool` plugin applies it when `tama` ticks.

## What it does

- **`tama-hook git commit`** -> `shipping` (pet picks up momentum)
- **`tama-hook git merge`** -> `shipping`
- **`tama-hook git rebase`** -> `looping` (pet senses going in circles)

You can also append JSONL manually with `"activity":"shipping"` (or any other valid slug) to `git_events.jsonl`.

## Invocation

Call `tama-hook git …` from Git hooks (for example `post-commit`) or from CI wrappers after a successful local merge.

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

Git hooks append JSONL to:

- default: `~/.cli-tamagotchi/git_events.jsonl`
- override: `$CLI_TAMAGOTCHI_HOME/git_events.jsonl`

The Tamagotchi app reads this file on each tick.

### Step 3: Add a Git hook (example: post-commit)

Create `.git/hooks/post-commit`:

```sh
#!/bin/sh
tama-hook git commit
```

Then:

```bash
chmod +x .git/hooks/post-commit
```

For merges and rebases, call `tama-hook git merge` or `tama-hook git rebase` from hooks or scripts where it makes sense for your workflow.

### Step 4: Verify

After a commit (or manual hook run):

```bash
tama status
```

Optional debug check:

```bash
tail -n 10 ~/.cli-tamagotchi/git_events.jsonl
```

## Hook commands reference

| Command | When fired | Pet effect |
|---------|------------|------------|
| `tama-hook git commit` | After a commit (typical: `post-commit`) | `shipping` |
| `tama-hook git merge` | After a merge you care about | `shipping` |
| `tama-hook git rebase` | After a rebase you care about | `looping` |

## Line format (JSONL)

Hooks write `{"activity":"<slug>","ts":...}`. Manual lines may add `"silent": true` to skip the log line.

## Requires

- `tama` and `tama-hook` on `$PATH`
- Git (for hook scripts)
- An existing pet (`tama`)
