"""
combat.py — Fully deterministic, AI-free combat engine.

ARCHITECTURAL GUARANTEE: No OpenAI call is ever made from this module.
All randomness comes from Python's random module (true dice rolls).
The AI may *suggest* a combat encounter, but it never controls outcomes.

Combat Model:
  - D20 system: roll a 20-sided die to determine hits/misses
  - Damage = roll result + player strength modifier
  - Enemies are simple dicts (expandable to a class later)
  - Combat resolves turn-by-turn until one side reaches 0 HP
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from game.player import Player


# ── Enemy Definitions ─────────────────────────────────────────────────────────

def make_enemy(
    name: str,
    hp: int,
    attack: int,
    defense: int,
    xp_reward: int,
    gold_reward: int,
    loot: Optional[list[str]] = None,
) -> dict:
    """
    Factory for enemy dictionaries. Using dicts (rather than a full class)
    keeps enemies lightweight and JSON-serializable for world state storage.
    """
    return {
        "name": name,
        "hp": hp,
        "max_hp": hp,
        "attack": attack,       # added to enemy's d20 roll
        "defense": defense,     # minimum roll needed to hit this enemy
        "xp_reward": xp_reward,
        "gold_reward": gold_reward,
        "loot": loot or [],
    }


# Pre-defined enemy templates (extend freely)
ENEMY_TEMPLATES: dict[str, dict] = {
    "goblin": make_enemy("Goblin Scout", hp=8, attack=2, defense=8, xp_reward=30, gold_reward=5, loot=["Rusty Dagger"]),
    "skeleton": make_enemy("Skeleton Warrior", hp=12, attack=3, defense=10, xp_reward=50, gold_reward=8, loot=["Bone Shard"]),
    "dark_wolf": make_enemy("Shadow Wolf", hp=15, attack=4, defense=9, xp_reward=60, gold_reward=0, loot=["Wolf Pelt"]),
    "cultist": make_enemy("Ashveil Cultist", hp=14, attack=5, defense=11, xp_reward=75, gold_reward=12, loot=["Ritual Scroll"]),
    "cave_troll": make_enemy("Cave Troll", hp=30, attack=6, defense=12, xp_reward=150, gold_reward=20, loot=["Troll Hide", "Crude Club"]),
}


def get_enemy(key: str) -> dict:
    """Return a fresh copy of an enemy template by key."""
    if key not in ENEMY_TEMPLATES:
        raise ValueError(f"Unknown enemy type: {key!r}. Available: {list(ENEMY_TEMPLATES)}")
    import copy
    return copy.deepcopy(ENEMY_TEMPLATES[key])


# ── Dice ──────────────────────────────────────────────────────────────────────

def roll_d20() -> int:
    """Roll a 20-sided die. Always use this — never ask the AI."""
    return random.randint(1, 20)

def roll_d6() -> int:
    return random.randint(1, 6)


# ── Combat Log ────────────────────────────────────────────────────────────────

@dataclass
class CombatLog:
    """Accumulates a human-readable record of a combat encounter."""
    rounds: list[str] = field(default_factory=list)
    outcome: str = ""          # "victory", "defeat", or "fled"
    xp_gained: int = 0
    gold_gained: int = 0
    loot_gained: list[str] = field(default_factory=list)

    def add(self, line: str) -> None:
        self.rounds.append(line)

    def full_text(self) -> str:
        return "\n".join(self.rounds) + (f"\n\n{self.outcome.upper()}" if self.outcome else "")


# ── Core Combat Resolution ────────────────────────────────────────────────────

class CombatSystem:
    """
    Manages a single combat encounter from start to finish.

    Usage:
        cs = CombatSystem(player, enemy_dict)
        log = cs.resolve()
        # log.outcome == "victory" | "defeat" | "fled"
    """

    FLEE_BASE_CHANCE = 0.4   # 40% base flee chance

    def __init__(self, player: Player, enemy: dict) -> None:
        self.player = player
        self.enemy = enemy
        self.log = CombatLog()

    def _player_hits(self, roll: int) -> bool:
        """Does a player's roll beat the enemy's defense threshold?"""
        return roll >= self.enemy["defense"]

    def _enemy_hits(self, roll: int) -> bool:
        """
        Enemy hits if their roll + attack beats a flat threshold of 10.
        (Players don't have a formal defense stat yet — easy to add.)
        """
        return (roll + self.enemy["attack"]) >= 10

    def _player_damage(self, roll: int) -> int:
        """Damage = roll result + strength modifier."""
        return roll + self.player.strength

    def _enemy_damage(self, roll: int) -> int:
        """Enemy damage = d6 + attack bonus."""
        return roll_d6() + self.enemy["attack"]

    def attempt_flee(self) -> bool:
        """
        Player attempts to flee. Chance increases with intelligence
        (smart fighters know when to run).
        """
        chance = self.FLEE_BASE_CHANCE + (self.player.intelligence * 0.02)
        return random.random() < chance

    def resolve_round(self, action: str) -> bool:
        """
        Process one combat round. Returns True if combat should continue.
        action: "attack" | "flee"
        """
        enemy_name = self.enemy["name"]

        # ── Player action ──
        if action == "flee":
            if self.attempt_flee():
                self.log.add("You dash into the shadows and escape!")
                self.log.outcome = "fled"
                return False
            else:
                self.log.add("You scramble to flee but the enemy cuts off your escape!")

        else:  # attack
            p_roll = roll_d20()
            if p_roll == 20:
                # Critical hit: double damage
                dmg = self._player_damage(p_roll) * 2
                self.enemy["hp"] -= dmg
                self.log.add(f"  🎲 CRITICAL HIT! You roll a 20 → {dmg} damage to {enemy_name}.")
            elif self._player_hits(p_roll):
                dmg = self._player_damage(p_roll)
                self.enemy["hp"] -= dmg
                self.log.add(f"  🎲 You roll {p_roll} → Hit! {dmg} damage to {enemy_name} "
                             f"(HP: {max(0, self.enemy['hp'])}/{self.enemy['max_hp']}).")
            else:
                self.log.add(f"  🎲 You roll {p_roll} → Miss. {enemy_name} dodges your blow.")

        # Check enemy death
        if self.enemy["hp"] <= 0:
            self._resolve_victory()
            return False

        # ── Enemy counter-attack ──
        e_roll = roll_d20()
        if self._enemy_hits(e_roll):
            dmg = self._enemy_damage(e_roll)
            actual = self.player.take_damage(dmg)
            self.log.add(f"  ⚔️  {enemy_name} strikes back → {actual} damage to you "
                         f"(HP: {self.player.hp}/{self.player.max_hp}).")
        else:
            self.log.add(f"  ⚔️  {enemy_name} swings wildly — you dodge.")

        # Check player death
        if not self.player.is_alive():
            self.log.add(f"\n💀 You have been slain by {enemy_name}...")
            self.log.outcome = "defeat"
            return False

        return True  # combat continues

    def _resolve_victory(self) -> None:
        """Apply XP, gold, and loot rewards on enemy death."""
        xp = self.enemy["xp_reward"]
        gold = self.enemy["gold_reward"]
        loot = self.enemy["loot"]

        levelled_up = self.player.gain_xp(xp)
        self.player.modify_gold(gold)
        for item in loot:
            self.player.add_item(item)

        self.log.xp_gained = xp
        self.log.gold_gained = gold
        self.log.loot_gained = loot
        self.log.outcome = "victory"

        self.log.add(
            f"\n✨ {self.enemy['name']} falls! "
            f"You gain {xp} XP and {gold} gold."
        )
        if loot:
            self.log.add(f"   Loot: {', '.join(loot)}")
        if levelled_up:
            self.log.add(
                f"\n🌟 LEVEL UP! You are now level {self.player.level}. "
                f"HP fully restored to {self.player.max_hp}."
            )

    def resolve(self) -> CombatLog:
        """
        Full auto-resolve loop. In the real game loop the engine calls
        resolve_round() interactively. This method is for testing or
        non-interactive resolution.
        """
        self.log.add(f"\n⚔️  Combat begins: {self.player.name} vs {self.enemy['name']}\n")
        continuing = True
        while continuing:
            continuing = self.resolve_round("attack")
        return self.log
