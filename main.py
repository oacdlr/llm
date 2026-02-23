"""
main.py — Punto de entrada del juego Maestro de Mazmorras AI.

Ejecutar con:
    python main.py

O para nueva partida:
    python main.py --new

Requisitos:
    Variable de entorno OPENAI_API_KEY configurada.
    pip install openai
"""

from __future__ import annotations

import os
import sys

from game.engine import GameEngine


def main() -> None:
    # ── API Key ───────────────────────────────────────────────────────────────
    api_key = "change_me"  #cambiar por openai_api_key
    if not api_key:
        print("Error: la variable de entorno OPENAI_API_KEY no está configurada.")
        print("  setx OPENAI_API_KEY 'sk-...'")
        sys.exit(1)

    # ── Engine Init ───────────────────────────────────────────────────────────
    engine = GameEngine(api_key=api_key, slow_print=True)

    # Start fresh if --new flag is passed
    if "--new" in sys.argv:
        print("Iniciando una nueva partida...")
        engine.reset()

    # ── Start ─────────────────────────────────────────────────────────────────
    try:
        engine.start()
    except KeyboardInterrupt:
        print("\n\nJuego interrumpido. Progreso guardado.")
        engine._save_all()
        sys.exit(0)


if __name__ == "__main__":
    main()
