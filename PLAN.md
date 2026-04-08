# cli-tamagotchi — Development Plan

**Vision:** cli-tamagotchi is a terminal-first virtual pet that grows with your coding habits. Care for it in the CLI via the `tama` command, and it becomes a reflection of your developer behavior.

**Created:** April 2026
**Last Updated:** April 2026
**Status:** Planning / Pre-development

---

## Phase 1 — Terminal Pet ✅

**Goal:** Build a fully playable CLI Tamagotchi that is lovable and interactive.

### Core Mechanics

- [ ] Life stages: Egg → Baby → Child → Teen → Adult → Elder → Death
- [ ] Stats: Hunger, Happiness, Health, Weight, Discipline
- [ ] Real-time decay (pet ages even when app is closed)
- [ ] Evolution paths based on care (Good / Normal / Poor)
- [ ] Sleep mechanics: lights on/off, affect stats
- [ ] Attention needs: calls for interaction
- [ ] Poop management and cleanliness
- [ ] Sickness events and recovery
- [ ] Auto-save pet state to `~/.cli-tamagotchi/`

### Terminal UI

- [ ] Animated ASCII sprites for each character and mood
- [ ] Color-coded stat bars for each stat
- [ ] Action menu with up to 8 actions (Feed, Play, Sleep, Clean, Discipline, etc.)
- [ ] Event log with real-time updates
- [ ] Screens: New Pet, Help, Graveyard

### Plugin System

- [ ] BasePlugin class with lifecycle hooks: `onTick`, `onEvent`, `onExternalEvent`
- [ ] Entry-point plugin discovery from `~/.cli-tamagotchi/plugins/`
- [ ] Example plugin: modify stats, add events
- [ ] Load/unload plugins dynamically without restarting CLI

### CLI Commands (`tama`)

- [ ] `tama` — Launch full TUI
- [ ] `tama status` — Show pet stats quickly
- [ ] `tama play` — Play mini-game
- [ ] `tama clean` — Clean pet
- [ ] `tama sleep` / `tama wake` — Toggle sleep
- [ ] `tama logs` — Show event log
- [ ] `tama graveyard` — View deceased pets
- [ ] `tama switch <pet_id>` — Switch between multiple pets

### Mini-Games

- [ ] Implement Play action mini-game (reaction/guess game)
- [ ] Track mini-game score to affect Happiness stat

### Multi-Pet Support

- [ ] Multiple pet slots
- [ ] Switch between pets easily via CLI

### Packaging

- [ ] Prepare PyPI package for `cli-tamagotchi`
- [ ] Documentation: README, CLI help, plugin guide

---

## Phase 2 — AI Agent Awareness 🔜

**Goal:** Pet reacts to coding activity and AI agents.

### Behavioral Classification

- [ ] Define coding activity states:
  - Shipping
  - Looping
  - Exploring
  - Blocked
  - Tests Passed
  - Tests Failed
  - Sub-agent Spawned
- [ ] Map pet reactions to each state (animations, stat changes, event logs)

### AI Tool Plugins

- [ ] Claude Code plugin — implement all behavior states
- [ ] Cursor plugin — read agent JSONL logs
- [ ] GitHub Copilot plugin — monitor completions
- [ ] Git plugin — reactions to commits, merges, rebases
- [ ] CI/CD plugin — celebrate pipelines, mourn failures

### Pet Memory

- [ ] Long-term memory of project history
- [ ] Reference past events in logs: "Last time you worked on X..."
- [ ] Detect recurring errors and regressions

---

## Phase 3 — Optional Social CLI Interaction 🔜

**Goal:** Pets can “meet” in shared CLI sessions (optional peer discovery).

- [ ] WebSocket-based peer discovery server (optional)
- [ ] Peer registration: announce CLI instance to peers
- [ ] Pet visit protocol: pets appear for limited time in peer terminals
- [ ] LAN discovery via mDNS or local network broadcast
- [ ] Optional: Tailscale support for remote teams

---

## Architecture Overview

**Terminal Client (Python)**

- Core Engine: handles ticks, stats, evolution, events
- TUI: ASCII animations, menus, logs (Textual or Rich)
- Plugin System: lifecycle hooks, external events, stat modifiers
- CLI commands: `tama` with subcommands

**Persistence**

- Save pet state in JSON, YAML, or SQLite under `~/.cli-tamagotchi/`
- Auto-save every tick or on key events
- Backup and recovery system

---

## Principles

1. Terminal is home; all interaction happens in CLI via `tama`.
2. Progression is earned, not bought.
3. Developer-native: works in any terminal, tmux-friendly.
4. Pet reflects real coding behavior.
5. Start small; perfect Phase 1 before AI plugins.

---

## Complete Task Checklist

- [ ] Define ASCII sprite sets for all moods and life stages
- [ ] Implement tick engine (stat decay, aging, evolution triggers)
- [ ] Implement core mechanics (sleep, feed, attention, play, sickness)
- [ ] Implement CLI commands (`tama`)
- [ ] Implement TUI (Textual/Rich)
- [ ] Implement event log and stats visualization
- [ ] Implement mini-game for Play
- [ ] Multi-pet support
- [ ] Plugin system with BasePlugin
- [ ] AI Agent plugin skeletons (Claude, Cursor, Copilot)
- [ ] Long-term memory and regression detection
- [ ] Peer CLI discovery system (optional)
- [ ] PyPI package preparation and documentation
- [ ] Testing and bug fixing for all features