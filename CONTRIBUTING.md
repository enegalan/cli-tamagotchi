# Contributing to cli-tamagotchi

Thanks for helping improve this project. `cli-tamagotchi` is early-stage; contributions are welcome.

## Ways to contribute

- **Bug reports:** Open an issue with steps to reproduce, expected vs actual behavior, and your Python version and OS if relevant.
- **Features or design changes:** Open an issue first for larger changes so maintainers can align on direction before you invest time.
- **Code and tests:** Fix bugs, add behavior, or improve tests following the workflow below.
- **Docs:** README, this file, or inline clarification where it helps others.

## Development setup

Requirements: **Python 3.9+** (see `pyproject.toml`).

```bash
git clone enegalan/cli-tamagotchi
cd cli-tamagotchi
python3 -m venv .venv
source .venv/bin/activate # Windows: .venv\Scripts\activate
pip install -e .
```

Run the CLI after install:

```bash
tama status
```

Without installing the `tama` script:

```bash
PYTHONPATH=src python3 -m cli_tamagotchi status
```

## Before you open a pull request

1. **Sync** your local `main` (or default branch) with upstream when applicable.
2. **Branch** from the default branch using a short, descriptive name (e.g. `fix/decay-sleep`, `feat/graveyard-list`).
3. **Implement** your change in `src/cli_tamagotchi/` and add or update tests under `tests/` when behavior changes.
4. **Run the test suite** and fix failures:

```bash
python3 -m unittest discover -s tests
```

5. **Commit** with clear messages (see [Commit messages](#commit-messages)).

## How to open a pull request (PR)

Use this flow if you do not have direct push access to the main repository.

### 1. Fork and clone

On the hosting site (e.g. GitHub), fork the repository. Clone **your fork**:

```bash
git clone https://github.com/enegalan/cli-tamagotchi.git
cd cli-tamagotchi
```

### 2. Create a branch

```bash
git checkout main
git pull
git checkout -b <branch-name>
```

### 3. Push your branch

```bash
git push -u origin <branch-name>
```

### 4. Open the PR

On the hosting site, open **Compare & pull request** from your branch into the **default branch** of the upstream repository.

Fill in the PR with:

- **What** you changed (and **why**, if it is not obvious).
- **How to verify** (commands you ran, e.g. `python3 -m unittest discover -s tests`).
- **Related issue** number if one exists.

Keep the PR focused: one logical change per PR is easier to review than unrelated edits bundled together.

### 5. Review and follow-up

Maintainers may ask for small changes. Push additional commits to the same branch; the PR updates automatically. When feedback is addressed, reply on the thread or resolve review comments as appropriate.

## Code expectations

- Follow patterns already used in `src/cli_tamagotchi/`.
- Use English for code, comments, and commit messages.
- Avoid unrelated refactors in the same PR as a feature or bugfix.

## License

By contributing, you agree your contributions are licensed under the project's **MIT** license, same as the rest of the repository.
