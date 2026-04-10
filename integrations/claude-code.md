# Tamagotchi — Claude Code Integration

Connect your pet to Claude Code so it reacts to your coding sessions.
Your pet mood and hunger move based on how the session goes.

## What it does

- **You are shipping** -> pet gets happier
- **You are looping** (same tool many times) -> pet gets hungrier
- **You are exploring** (`read`, `grep`, etc.) -> mostly neutral
- **You are blocked** (tool errors) -> pet mood drops
- **Session ends** -> pet gets a small positive event

## Invocation

```text
/setup-tamagotchi-hooks
```

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

Claude hooks append JSONL events to:

- default: `~/.cli-tamagotchi/claude_events.jsonl`
- override: `$CLI_TAMAGOTCHI_HOME/claude_events.jsonl`

The Tamagotchi app reads this file on each tick.

### Step 3: Add hooks to Claude Code settings

Add this to `~/.claude/settings.json` (or `settings.local.json`):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "tama-hook pre-tool $CLAUDE_TOOL_NAME"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "tama-hook post-tool $CLAUDE_TOOL_NAME $CLAUDE_TOOL_EXIT_CODE $CLAUDE_TOOL_INPUT"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "tama-hook stop $CLAUDE_STOP_REASON"
          }
        ]
      }
    ],
    "SubagentStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "tama-hook subagent-start"
          }
        ]
      }
    ]
  }
}
```

### Step 4: Verify

Run a Claude Code session, then check:

```bash
tama status
```

Optional debug check:

```bash
tail -n 10 ~/.cli-tamagotchi/claude_events.jsonl
```

## Hook commands reference

| Command | When fired | Pet effect |
|---------|------------|------------|
| `tama-hook pre-tool <tool>` | Before any tool call | Logs tool usage for behavior classification |
| `tama-hook post-tool <tool> <exit> [command...]` | After a tool returns | Updates session behavior and outcomes |
| `tama-hook stop <reason>` | When session ends | Emits final session event |
| `tama-hook subagent-start` | When a subagent starts | `sub_agent_spawned` reaction |
| `tama-hook claude activity <slug>` | Manual / scripts | Same slugs as core `CodingActivity` (e.g. `tests_passed`) |

## Behavioral states

The plugin classifies your session as:

- **SHIPPING**: productive write/edit/execute patterns
- **LOOPING**: repeated tool usage patterns
- **EXPLORING**: mostly read/search activity
- **BLOCKED**: repeated tool failures
- **WORKING**: neutral baseline (no periodic stat nudge)

## Requires

- `tama` and `tama-hook` on `$PATH`
- Claude Code hooks support
- An existing pet (`tama`)
