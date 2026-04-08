# cli-tamagotchi — Development Plan

**Vision:** cli-tamagotchi is a terminal-first virtual pet that grows with your coding habits. Care for it in the CLI via the `tama` command, and it becomes a reflection of your developer behavior.

**Created:** April 2026
**Last Updated:** April 2026
**Status:** Planning / Pre-development

---

## Phase 1 — Terminal Pet ✅

**Goal:** Build a fully playable CLI Tamagotchi that is lovable and interactive.

### Core Mechanics

- [X] Life stages: Egg → Baby → Child → Teen → Adult → Elder → Death
- [X] Stats: Character, Stage, Weight, State (Wake or Asleep), Dirtiness, Hunger, Happiness, Health.
- [X] Real-time decay (pet ages even when app is closed)
- [X] Evolution paths based on care (Good / Normal / Poor)
- [X] Sleep mechanics: lights on/off, affect stats
- [X] Attention needs: calls for interaction
- [X] Poop management and cleanliness
- [X] Sickness events and recovery
- [X] Auto-save pet state to `~/.cli-tamagotchi/`

### Terminal UI

- [X] Animated ASCII sprites for each character and mood
- [X] Color-coded stat bars for each stat
- [X] Action menu with up to 8 actions (Feed, Play, Lights On/Off, Clean, Status, etc.)
- [X] Event log with real-time updates
- [ ] Screens:
  - [X] New Pet
  - [X] Help
  - [X] Graveyard

### Plugin System

- [ ] BasePlugin class with lifecycle hooks: `onTick`, `onEvent`, `onExternalEvent`
- [ ] Entry-point plugin discovery from `~/.cli-tamagotchi/plugins/`
- [ ] Example plugin: modify stats, add events
- [ ] Load/unload plugins dynamically without restarting CLI

### CLI Commands (`tama`)

- [X] `tama` — Launch full TUI
- [X] `tama status` — Show pet stats quickly
- [X] `tama feed` — Feed pet
- [X] `tama play` — Play mini-game
- [X] `tama lights` — Toggle the lights on or off.
- [X] `tama clean` — Clean pet
- [X] `tama medicine` — Give medicine
- [X] `tama new` — Start a new pet
- [ ] `tama logs` — Show event log
- [X] `tama graveyard` — View deceased pets

### Mini-Games

- [ ] Implement Play action mini-game (reaction/guess game)
- [ ] Track mini-game score to affect Happiness stat

### Packaging

- [ ] Prepare PyPI package for `cli-tamagotchi`
- [ ] Documentation:
  - [X] README,
  - [X] CLI help
  - [ ] plugin guide

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
