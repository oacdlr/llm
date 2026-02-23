"""
engine.py — El GameEngine: orquestador de todos los sistemas.

El engine es la única clase que mantiene referencias a todos los subsistemas y
coordina el flujo de un único turno de juego:

    1. Obtener input del jugador
    2. Preguntar a la IA por narrativa + señales de eventos
    3. Aplicar lógica determinista (combate, actualizaciones del mundo, memoria)
    4. Guardar estado
    5. Mostrar resultados

Nota de arquitectura: el engine es deliberadamente ligero en lógica de negocio.
La lógica pesada vive en las clases de dominio (Player, WorldState, CombatSystem).
El engine solo las conecta en el orden correcto.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Optional

from game.player import Player
from game.world import WorldState
from game.combat import CombatSystem, get_enemy
from game.memory import MemorySystem
from ai.dungeon_master import DungeonMaster, DMResponse


# ── Display Helpers ───────────────────────────────────────────────────────────

DIVIDER = "═" * 60

def _print_slow(text: str, delay: float = 0.018) -> None:
    """Efecto de máquina de escribir para texto narrativo."""
    for char in text:
        print(char, end="", flush=True)
        time.sleep(delay)
    print()

def _header(text: str) -> None:
    print(f"\n{DIVIDER}")
    print(f"  {text}")
    print(DIVIDER)

def _section(title: str) -> None:
    print(f"\n── {title} {'─' * (54 - len(title))}")


# ── Game Engine ───────────────────────────────────────────────────────────────

class GameEngine:
    """
    Coordinador central del juego Maestro de Mazmorras AI.

    Posee una instancia de cada subsistema y media toda la comunicación
    entre sistemas. El código externo (main.py) solo interactúa con esta clase.
    """

    def __init__(self, api_key: str, slow_print: bool = True) -> None:
        self.player = Player.load()
        self.world = WorldState.load()
        self.memory = MemorySystem.load()
        self.dm = DungeonMaster(api_key=api_key)
        self.slow_print = slow_print
        self._running = False

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Punto de entrada: mostrar introducción e iniciar el bucle de juego."""
        self._show_intro()
        self._running = True
        self._game_loop()

    def reset(self) -> None:
        """Borrar datos guardados y comenzar desde cero — usado para nueva partida."""
        self.player = Player()
        self.world = WorldState()
        self.memory = MemorySystem()
        self._save_all()

    # ── Game Loop ─────────────────────────────────────────────────────────────

    def _game_loop(self) -> None:
        """
        Main turn loop. Each iteration:
          1. Show status
          2. Get action
          3. Run AI
          4. Apply results
          5. Maybe combat
          6. Save
        """
        # Comenzar con una escena de apertura
        opening = self._get_narrative("Llego y observo mi alrededor.")
        self._display_narrative(opening.narrative)

        while self._running and self.player.is_alive():
            self.world.increment_turn()
            _section(f"Turn {self.world.turn_count} — {self.world.location}")
            print(self.player.status_str())

            action = self._get_player_input()
            if action is None:
                break

            # Comprimir memoria si hace falta
            if self.memory.should_summarize():
                print("\n[Actualizando la crónica...]")
                summary = self.dm.summarize_memory(self.memory.events)
                self.memory.summaries.append(summary)
                self.memory.events.clear()

            # Llamar a la IA
            print("\n[El maestro de mazmorras medita...]")
            response = self._get_narrative(action)

            # Apply world changes from AI response
            self._apply_world_changes(response)

            # Mostrar la narrativa
            _section("La Historia")
            self._display_narrative(response.narrative)

            # Handle combat if triggered
            if response.combat_trigger and response.enemy_type:
                self._run_combat(response.enemy_type)
            elif response.combat_trigger:
                # La IA desencadenó combate pero no dio tipo de enemigo válido — por defecto: goblin
                print("\n[Engine: la IA lanzó combate sin tipo de enemigo — usando goblin por defecto]")
                self._run_combat("goblin")

            # Registrar evento en la memoria
            if response.memory_event:
                self.memory.record(response.memory_event)
            else:
                self.memory.record(f"Turno {self.world.turn_count}: {action[:80]}")

            # Notificación de actualización de misión
            if response.quest_update:
                _section("Actualización de misión")
                print(f"📜 {response.quest_update}")
                self.world.set_quest(response.quest_update)

            # Check death after combat
            if not self.player.is_alive():
                self._handle_death()
                break

            self._save_all()

        if self._running:
            self._show_outro()

    # ── Input ─────────────────────────────────────────────────────────────────

    def _get_player_input(self) -> Optional[str]:
        """
        Read player input. Returns None on quit/EOF.
        Also handles meta-commands (inventory, status, help).
        """
        while True:
            try:
                raw = input("\n> ¿Qué haces? ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nAdiós, aventurero.")
                return None

            if not raw:
                continue

            lower = raw.lower()

            # Meta-commands (handled by engine, not AI)
            if lower in ("quit", "exit", "q"):
                print("Guardando y saliendo...")
                self._save_all()
                return None
            if lower in ("inventory", "inv", "i"):
                self._show_inventory()
                continue
            if lower in ("status", "stats", "s"):
                print(self.player.status_str())
                continue
            if lower in ("help", "h", "?"):
                self._show_help()
                continue
            if lower in ("memory", "journal"):
                print("\n" + self.memory.get_context_block())
                continue
            if lower in ("world", "location"):
                print(f"\nUbicación: {self.world.location}")
                print(f"Misión: {self.world.active_quest or 'Ninguna'}")
                print(f"PNJs conocidos: {[n['name'] for n in self.world.known_npcs]}")
                continue

            return raw

    # ── AI Interface ──────────────────────────────────────────────────────────

    def _get_narrative(self, action: str) -> DMResponse:
        """
        Package current game state and send to the Dungeon Master AI.
        Returns a validated DMResponse.
        """
        return self.dm.narrate(
            player_dict=self.player.to_dict(),
            world_context=self.world.to_ai_context(),
            memory_block=self.memory.get_context_block(),
            player_action=action,
        )

    # ── World Application ─────────────────────────────────────────────────────

    def _apply_world_changes(self, response: DMResponse) -> None:
        """
        Apply non-combat changes signalled by the AI response.
        All changes go through proper setter methods — never raw attribute access.
        """
        if response.new_npc:
            npc = response.new_npc
            self.world.add_npc(npc["name"], npc["role"], npc["disposition"])
            print(f"\n[Nuevo PNJ encontrado: {npc['name']} — {npc['role']}]")

        if response.new_location:
            self.world.move_to(
                response.new_location,
                response.location_description or "",
            )
            print(f"\n📍 Ubicación: {response.new_location}")

        if response.tension_delta != 0.0:
            self.world.adjust_tension(response.tension_delta)

    # ── Combat ────────────────────────────────────────────────────────────────

    def _run_combat(self, enemy_type: str) -> None:
        """
        Manage an interactive combat encounter.

        The AI triggered this fight, but from here on every outcome is
        determined by dice and Python math — zero AI involvement.
        """
        try:
            enemy = get_enemy(enemy_type)
        except ValueError as exc:
            print(f"\n[Engine error: {exc}]")
            return

        _header(f"⚔️  COMBATE: ¡{enemy['name']} aparece!")
        print(f"Enemigo — PV: {enemy['hp']} | ATQ: {enemy['attack']} | DEF: {enemy['defense']}")
        self.world.adjust_tension(0.5)   # el combate siempre aumenta la tensión

        combat = CombatSystem(self.player, enemy)

        while True:
            print(f"\n{self.player.status_str()}")
            print(f"Enemy: {enemy['name']} HP {enemy['hp']}/{enemy['max_hp']}")
            print("\n[A]ttack | [F]lee")

            try:
                choice = input("> ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "flee"

            if choice in ("a", "attack", ""):
                action = "attack"
            elif choice in ("f", "flee"):
                action = "flee"
            else:
                print("Atacar o huir — elige con sabiduría.")
                continue

            still_fighting = combat.resolve_round(action)

            # Print the latest combat log entry
            if combat.log.rounds:
                print(combat.log.rounds[-1])

            if not still_fighting:
                break

        # Display final combat summary
        _section("Fin del combate")
        outcome = combat.log.outcome
        if outcome == "victory":
            print(f"✨ ¡Victoria! XP: +{combat.log.xp_gained} | Oro: +{combat.log.gold_gained}g")
            if combat.log.loot_gained:
                print(f"   Botín obtenido: {', '.join(combat.log.loot_gained)}")
            self.world.adjust_tension(-0.3)
            self.memory.record(
                f"Derrotado un {enemy['name']} en combate. "
                f"Obtuviste {combat.log.xp_gained} XP y {combat.log.gold_gained} oro."
            )
        elif outcome == "defeat":
            print("💀 Has caído...")
            self.memory.record(f"Asesinado por un {enemy['name']}.")
        elif outcome == "fled":
            print("💨 Huiste, pero el peligro persiste.")
            self.world.adjust_tension(0.2)
            self.memory.record(f"Huiste de un {enemy['name']}.")

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_all(self) -> None:
        """Guardar todo el estado del juego de forma atómica."""
        self.player.save()
        self.world.save()
        self.memory.save()

    # ── Display ───────────────────────────────────────────────────────────────

    def _display_narrative(self, text: str) -> None:
        print()
        if self.slow_print:
            _print_slow(text)
        else:
            print(text)

    def _show_intro(self) -> None:
        print("\n" + "▓" * 60)
        print("  ⚔️   M A E S T R O   D E   M A Z M O R R A S   ⚔️")
        print("▓" * 60)
        print("\nTe espera una fantasía oscura. Escribe tus acciones libremente.")
        print("Comandos: [inventory] [status] [memory] [world] [quit]")
        print()
        if self.player.name == "Adventurer" and self.world.turn_count == 0:
            print("Parece ser una nueva partida.")
            try:
                name = input("¿Cuál es tu nombre, viajero? ").strip()
                if name:
                    self.player.name = name
            except (EOFError, KeyboardInterrupt):
                pass

    def _show_outro(self) -> None:
        _header("La historia continúa...")
        print("Tu progreso ha sido guardado.")
        print(f"Turnos jugados: {self.world.turn_count}")

    def _handle_death(self) -> None:
        _header("HAS MUERTO")
        print("La oscuridad te reclama. Tu crónica termina aquí.")
        print("\nEstadísticas finales:")
        print(self.player.status_str())
        print(f"Turnos sobrevividos: {self.world.turn_count}")
        print("\nComenzando una nueva vida...")
        time.sleep(2)
        self.reset()

    def _show_inventory(self) -> None:
        _section("Inventario")
        if self.player.inventory:
            for item in self.player.inventory:
                print(f"  • {item}")
        else:
            print("  (vacío)")
        print(f"  Gold: {self.player.gold}g")

    def _show_help(self) -> None:
        _section("Ayuda")
        print("  Escribe cualquier acción en texto libre — el DM responderá.")
        print("  Ejemplos:")
        print("    'Registro la habitación con cuidado'")
        print("    'Hablo con el posadero'")
        print("    'Desenfundo mi espada y avanzo'")
        print("    'Intento forzar la cerradura'")
        print("\n  Comandos especiales:")
        print("    inventory / inv   — mostrar tus objetos")
        print("    status / stats    — mostrar tus estadísticas")
        print("    memory / journal  — mostrar la crónica")
        print("    world / location  — mostrar información del mundo")
        print("    quit / exit       — guardar y salir")
