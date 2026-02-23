"""
world.py — Persistent world state.

The WorldState holds everything about the game world that isn't the player:
location, known NPCs, active quests, and a global tension score that
affects how the AI frames its narrative.

Architecture note: Only this class and the engine may mutate world state.
The AI reads it (via a serialized snapshot) but never writes it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


SAVE_PATH = Path(__file__).parent.parent / "data" / "world_state.json"

# Starting world configuration
DEFAULT_LOCATION = "The Broken Flagon Inn, Ashenveil"
DEFAULT_REGION_DESC = (
    "A dying frontier town where the candles burn low and strangers are watched "
    "with hollow eyes. The forest beyond the walls hums with something old and hungry."
)


class WorldState:
    """
    Tracks all mutable world data: where the player is, who they've met,
    what quests are active, and a tension score (0-10) used to tune
    the darkness/urgency of AI-generated narrative.
    """

    def __init__(
        self,
        location: str = DEFAULT_LOCATION,
        region_description: str = DEFAULT_REGION_DESC,
        active_quest: Optional[str] = None,
        known_npcs: Optional[list[dict]] = None,
        tension: float = 3.0,
        turn_count: int = 0,
        visited_locations: Optional[list[str]] = None,
        world_flags: Optional[dict] = None,
    ) -> None:
        self.location = location
        self.region_description = region_description
        self.active_quest = active_quest
        self.known_npcs: list[dict] = known_npcs or []
        # tension: 0 = peaceful, 10 = apocalyptic
        self.tension: float = max(0.0, min(10.0, tension))
        self.turn_count = turn_count
        self.visited_locations: list[str] = visited_locations or [location]
        # Freeform boolean flags for quest/story state
        self.world_flags: dict = world_flags or {}

    # ── Mutation Methods ──────────────────────────────────────────────────────

    def move_to(self, new_location: str, description: str = "") -> None:
        """Change current location and log it to visited list."""
        self.location = new_location
        if description:
            self.region_description = description
        if new_location not in self.visited_locations:
            self.visited_locations.append(new_location)

    def set_quest(self, quest: Optional[str]) -> None:
        """Set or clear the active quest."""
        self.active_quest = quest

    def add_npc(self, name: str, role: str, disposition: str = "neutral") -> None:
        """Register a new NPC into the world. Skips duplicates by name."""
        if not any(npc["name"] == name for npc in self.known_npcs):
            self.known_npcs.append({
                "name": name,
                "role": role,
                "disposition": disposition,
            })

    def update_npc_disposition(self, name: str, disposition: str) -> bool:
        """Update how an NPC feels about the player. Returns False if NPC unknown."""
        for npc in self.known_npcs:
            if npc["name"] == name:
                npc["disposition"] = disposition
                return True
        return False

    def adjust_tension(self, delta: float) -> None:
        """Nudge the tension score, clamped to [0, 10]."""
        self.tension = max(0.0, min(10.0, self.tension + delta))

    def set_flag(self, key: str, value: bool = True) -> None:
        """Set a world flag (e.g. 'boss_defeated', 'bridge_destroyed')."""
        self.world_flags[key] = value

    def get_flag(self, key: str) -> bool:
        return self.world_flags.get(key, False)

    def increment_turn(self) -> None:
        self.turn_count += 1

    # ── Persistence ───────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "location": self.location,
            "region_description": self.region_description,
            "active_quest": self.active_quest,
            "known_npcs": self.known_npcs,
            "tension": self.tension,
            "turn_count": self.turn_count,
            "visited_locations": self.visited_locations,
            "world_flags": self.world_flags,
        }

    def save(self, path: Path = SAVE_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path = SAVE_PATH) -> "WorldState":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        return cls(**data)

    # ── Snapshot for AI ───────────────────────────────────────────────────────

    def to_ai_context(self) -> dict:
        """
        Return a clean dict suitable for injecting into the AI system prompt.
        Excludes internal bookkeeping fields the AI doesn't need.
        """
        return {
            "current_location": self.location,
            "location_atmosphere": self.region_description,
            "active_quest": self.active_quest or "None",
            "known_npcs": self.known_npcs,
            "world_tension": self.tension,
            "notable_flags": {k: v for k, v in self.world_flags.items() if v},
        }

    def __repr__(self) -> str:
        return f"WorldState(location={self.location!r}, tension={self.tension}, turn={self.turn_count})"
