"""
player.py — Player entity and stat management.

The Player class is the authoritative source of truth for all player data.
No other system (especially not the AI) is allowed to modify player stats directly.
All mutations go through explicit methods so logic stays auditable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


SAVE_PATH = Path(__file__).parent.parent / "data" / "player_state.json"


class Player:
    """
    Represents the player character with full stat tracking.

    Architecture note: All stat changes are method-driven so the rest of the
    engine can log, validate, or hook into changes without reaching into raw attrs.
    """

    def __init__(
        self,
        name: str = "Adventurer",
        hp: int = 20,
        max_hp: int = 20,
        strength: int = 5,
        intelligence: int = 5,
        gold: int = 10,
        inventory: Optional[list[str]] = None,
        level: int = 1,
        xp: int = 0,
    ) -> None:
        self.name = name
        self.hp = hp
        self.max_hp = max_hp
        self.strength = strength
        self.intelligence = intelligence
        self.gold = gold
        self.inventory: list[str] = inventory if inventory is not None else ["Torch", "Rations x3"]
        self.level = level
        self.xp = xp

    # ── Stat Mutation Methods ─────────────────────────────────────────────────

    def take_damage(self, amount: int) -> int:
        """Apply damage, clamping HP to 0. Returns actual damage dealt."""
        actual = min(amount, self.hp)
        self.hp = max(0, self.hp - amount)
        return actual

    def heal(self, amount: int) -> int:
        """Restore HP up to max_hp. Returns amount actually healed."""
        actual = min(amount, self.max_hp - self.hp)
        self.hp = min(self.max_hp, self.hp + amount)
        return actual

    def gain_xp(self, amount: int) -> bool:
        """Add XP and check for level-up. Returns True if levelled up."""
        self.xp += amount
        threshold = self.level * 100
        if self.xp >= threshold:
            self.xp -= threshold
            self._level_up()
            return True
        return False

    def _level_up(self) -> None:
        """Private: apply level-up bonuses."""
        self.level += 1
        self.max_hp += 5
        self.hp = self.max_hp          # full heal on level up
        self.strength += 1
        self.intelligence += 1

    def add_item(self, item: str) -> None:
        """Add an item to inventory."""
        self.inventory.append(item)

    def remove_item(self, item: str) -> bool:
        """Remove an item by name. Returns False if not found."""
        if item in self.inventory:
            self.inventory.remove(item)
            return True
        return False

    def modify_gold(self, delta: int) -> bool:
        """
        Add or subtract gold. Negative delta = spending.
        Returns False if the player can't afford it.
        """
        if self.gold + delta < 0:
            return False
        self.gold += delta
        return True

    # ── Persistence ───────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize player state for saving or injecting into AI prompts."""
        return {
            "name": self.name,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "strength": self.strength,
            "intelligence": self.intelligence,
            "gold": self.gold,
            "inventory": self.inventory,
            "level": self.level,
            "xp": self.xp,
        }

    def save(self, path: Path = SAVE_PATH) -> None:
        """Write player state to JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path = SAVE_PATH) -> "Player":
        """Load player from JSON, or return a default player if no save exists."""
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        return cls(**data)

    # ── Display ───────────────────────────────────────────────────────────────

    def status_str(self) -> str:
        """Short status line for display in the terminal."""
        bar_len = 10
        filled = int((self.hp / self.max_hp) * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        return (
            f"[{self.name} | Lv.{self.level} | HP: {bar} {self.hp}/{self.max_hp} | "
            f"STR:{self.strength} INT:{self.intelligence} | Gold:{self.gold}g]"
        )

    def is_alive(self) -> bool:
        return self.hp > 0

    def __repr__(self) -> str:
        return f"Player(name={self.name!r}, hp={self.hp}/{self.max_hp}, level={self.level})"
