from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .models import PetState


class PetStorage:
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = base_dir or Path.home() / ".cli-tamagotchi"
        self.pet_path = self.base_dir / "pet.json"

    def ensure_dir(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def exists(self) -> bool:
        return self.pet_path.exists()

    def load(self) -> Optional[PetState]:
        if not self.exists():
            return None

        payload = json.loads(self.pet_path.read_text(encoding="utf-8"))
        return PetState.from_dict(payload)

    def save(self, pet_state: PetState) -> None:
        self.ensure_dir()
        serialized_state = json.dumps(pet_state.to_dict(), indent=2)
        self.pet_path.write_text(serialized_state + "\n", encoding="utf-8")

    def can_create_new_pet(self, current_pet: PetState) -> bool:
        """Single-slot save: a new egg is only allowed when the current record is not alive."""
        return not current_pet.is_alive
