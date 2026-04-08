from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .graveyard import GraveyardEntry, append_graveyard_entry, read_graveyard, snapshot_from_dead_pet
from .models import PetState


class PetStorage:
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = base_dir or Path.home() / ".cli-tamagotchi"
        self.pet_path = self.base_dir / "pet.json"
        self.graveyard_path = self.base_dir / "graveyard.json"

    def ensure_dir(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def exists(self) -> bool:
        return self.pet_path.exists()

    def load(self) -> Optional[PetState]:
        if not self.exists():
            return None

        payload = json.loads(self.pet_path.read_text(encoding="utf-8"))
        return PetState.from_dict(payload)

    def load_graveyard(self) -> list[GraveyardEntry]:
        return read_graveyard(self.graveyard_path)

    def save(self, pet_state: PetState) -> None:
        self.ensure_dir()
        if not pet_state.is_alive and pet_state.graveyard_needs_entry:
            append_graveyard_entry(self.graveyard_path, snapshot_from_dead_pet(pet_state))
            pet_state.graveyard_needs_entry = False

        serialized_state = json.dumps(pet_state.to_dict(), indent=2)
        self.pet_path.write_text(serialized_state + "\n", encoding="utf-8")

    def can_create_new_pet(self, current_pet: PetState) -> bool:
        """Single-slot save: a new egg is only allowed when the current record is not alive."""
        return not current_pet.is_alive

    def save_dead_before_hatching_replacement(self, dead_pet_state: PetState) -> None:
        """Persist the dead pet (and append graveyard if pending) before save is overwritten by a new egg."""
        if dead_pet_state.is_alive:
            return
        self.save(dead_pet_state)
