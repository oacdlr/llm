"""
dungeon_master.py — Capa de interfaz con la IA.

Esta clase es el ÚNICO lugar del proyecto que se comunica con OpenAI.
Recibe un estado de juego estructurado y devuelve una respuesta validada y tipada.

Nota de arquitectura: DungeonMaster es un traductor puro — recibe "estado de juego"
y produce "intención narrativa estructurada". Nunca toca objetos Player o WorldState.
Esos son gestionados exclusivamente por el GameEngine.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from openai import OpenAI

from ai.prompts import SYSTEM_PROMPT, build_user_message


# ── Response Schema ───────────────────────────────────────────────────────────

@dataclass
class DMResponse:
    """
    Contenedor validado y fuertemente tipado para la respuesta de la IA.

    Cada campo tiene un valor por defecto seguro para que respuestas parciales no
    hagan fallar el motor. El engine lee estos campos y decide qué hacer — nunca
    confía en el texto crudo de la IA.
    """
    narrative: str = "The shadows stir. Something is watching."
    combat_trigger: bool = False
    enemy_type: Optional[str] = None
    new_npc: Optional[dict] = None         # {name, role, disposition}
    quest_update: Optional[str] = None
    new_location: Optional[str] = None
    location_description: Optional[str] = None
    tension_delta: float = 0.0
    memory_event: Optional[str] = None
    raw_json: dict = field(default_factory=dict)    # for debugging


# ── Dungeon Master ────────────────────────────────────────────────────────────

class DungeonMaster:
    """
    Envuelve la API de OpenAI y traduce estado de juego → intención narrativa.

    Responsabilidades:
        - Construir el prompt desde plantillas (ai/prompts.py)
        - Llamar a la API con manejo seguro de errores/reintentos
        - Parsear y validar la respuesta JSON
        - Devolver un DMResponse seguro (no lanza por rarezas de la IA)
    """

    MODEL = "gpt-4o-mini"
    MAX_TOKENS = 600
    TEMPERATURE = 0.92       # slightly high for creative narrative variance

    # Valid enemy types (must match combat.py ENEMY_TEMPLATES keys)
    VALID_ENEMY_TYPES = {"goblin", "skeleton", "dark_wolf", "cultist", "cave_troll"}

    def __init__(self, api_key: str) -> None:
        self.client = OpenAI(api_key=api_key)
        # Maintain a short conversation history for continuity within a session.
        # We reset on new sessions but keep it alive across turns in a run.
        self._history: list[dict] = []

    def narrate(
        self,
        player_dict: dict,
        world_context: dict,
        memory_block: str,
        player_action: str,
    ) -> DMResponse:
        """
        Main entry point. Accepts serialized game state, returns DMResponse.

        The AI is called once per turn. We use a hybrid approach:
          - System prompt is always the full SYSTEM_PROMPT (stateless context).
          - We pass recent history for within-session continuity (up to 6 turns).
          - The user message always includes the full current game state snapshot,
            so the AI stays grounded even if history drifts.
        """
        user_message = build_user_message(
            player_dict, world_context, memory_block, player_action
        )

        # Append to local history (trimmed to last 6 exchanges = 12 messages)
        self._history.append({"role": "user", "content": user_message})
        if len(self._history) > 12:
            self._history = self._history[-12:]

        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self._history

        try:
            completion = self.client.chat.completions.create(
                model=self.MODEL,
                messages=messages,
                max_tokens=self.MAX_TOKENS,
                temperature=self.TEMPERATURE,
                response_format={"type": "json_object"},   # forzar modo JSON
            )
            raw_text = completion.choices[0].message.content.strip()
            # Registrar respuesta del asistente en el historial
            self._history.append({"role": "assistant", "content": raw_text})

        except Exception as exc:
            # Fallo de red/API: devolver respuesta segura de reserva
            print(f"\n[DM Aviso] error de API: {exc}")
            return DMResponse(
                narrative="La mazmorra contiene la respiración. El mundo espera.",
                memory_event=f"[Error de API en el turno — acción: {player_action[:60]}]",
            )

        return self._parse(raw_text)

    def summarize_memory(self, events: list[str]) -> str:
        """
        Separate call used by MemorySystem to compress event logs.
        Extracted here so all API calls go through DungeonMaster.
        """
        events_text = "\n".join(f"- {e}" for e in events)
        prompt = (
            "You are a dark fantasy chronicle keeper. Compress these game events "
            "into a single vivid paragraph (2-4 sentences), past tense, omniscient "
            "narrator. Preserve all important facts. Be atmospheric but concise.\n\n"
            f"Events:\n{events_text}"
        )
        try:
            resp = self.client.chat.completions.create(
                model=self.MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.7,
            )
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            return f"[Resumen fallido: {exc}] " + " | ".join(events)

    # ── JSON Parsing & Validation ─────────────────────────────────────────────

    def _parse(self, raw_text: str) -> DMResponse:
        """
        Safely parse the AI's JSON response into a DMResponse.

        We validate every field individually so a malformed AI response
        can never crash the game or inject bad data into game state.
        """
        # Strip markdown fences if the model adds them despite json_object mode
        clean = re.sub(r"```(?:json)?|```", "", raw_text).strip()

        try:
            data = json.loads(clean)
        except json.JSONDecodeError as exc:
            print(f"\n[DM Aviso] fallo al parsear JSON: {exc}\nRaw: {raw_text[:200]}")
            return DMResponse(
                narrative=self._extract_narrative_fallback(raw_text),
            )

        # Validate fields one by one — never trust the AI blindly
        narrative = self._safe_str(data.get("narrative"), "The world holds its breath.")

        combat_trigger = bool(data.get("combat_trigger", False))

        enemy_type = data.get("enemy_type")
        if enemy_type not in self.VALID_ENEMY_TYPES:
            enemy_type = None   # silently discard invalid enemy types
        if not combat_trigger:
            enemy_type = None   # no combat = no enemy

        new_npc = self._validate_npc(data.get("new_npc"))
        quest_update = self._safe_str(data.get("quest_update"), None)
        new_location = self._safe_str(data.get("new_location"), None)
        location_description = self._safe_str(data.get("location_description"), None)
        memory_event = self._safe_str(data.get("memory_event"), None)

        # Limitar tension_delta a un rango seguro para que la IA no eleve la tensión a 10
        try:
            tension_delta = float(data.get("tension_delta", 0.0))
            tension_delta = max(-1.0, min(1.0, tension_delta))
        except (TypeError, ValueError):
            tension_delta = 0.0

        return DMResponse(
            narrative=narrative,
            combat_trigger=combat_trigger,
            enemy_type=enemy_type,
            new_npc=new_npc,
            quest_update=quest_update,
            new_location=new_location,
            location_description=location_description,
            tension_delta=tension_delta,
            memory_event=memory_event,
            raw_json=data,
        )

    @staticmethod
    def _safe_str(value, default) -> Optional[str]:
        """Devuelve un string si es válido, si no el valor por defecto."""
        if isinstance(value, str) and value.strip() and value.lower() != "null":
            return value.strip()
        return default

    @staticmethod
    def _validate_npc(npc_data) -> Optional[dict]:
        """Validar la estructura del dict NPC. Devuelve None si está malformado."""
        if not isinstance(npc_data, dict):
            return None
        name = npc_data.get("name", "")
        role = npc_data.get("role", "stranger")
        disposition = npc_data.get("disposition", "neutral")
        if not isinstance(name, str) or not name.strip():
            return None
        if disposition not in {"friendly", "neutral", "hostile"}:
            disposition = "neutral"
        return {"name": name.strip(), "role": role, "disposition": disposition}

    @staticmethod
    def _extract_narrative_fallback(text: str) -> str:
        """Último recurso: extraer algo legible de una respuesta rota."""
        # Intentar encontrar un valor "narrative" incluso en JSON malformado
        match = re.search(r'"narrative"\s*:\s*"([^\"]{10,})"', text)
        if match:
            return match.group(1)
        # Devolver los primeros 200 caracteres de lo que dijo la IA
        return text[:200].strip() or "La mazmorra guarda sus secretos."
