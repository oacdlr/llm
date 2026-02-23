# ⚔️ Maestro de Mazmorras AI

Un RPG de fantasía oscura, modular y basado en terminal, impulsado por Python y la API de OpenAI.

## Arquitectura

```
ai_dungeon/
├── main.py               # Punto de entrada
├── game/
│   ├── player.py         # Estadísticas del jugador, inventario, guardar/cargar
│   ├── world.py          # Estado del mundo, PNJ, misiones, tensión
│   ├── combat.py         # Motor de combate determinista D20
│   ├── memory.py         # Registro de eventos + compresión de memoria AI
│   └── engine.py         # Orquestador del bucle de juego
├── ai/
│   ├── dungeon_master.py # Envoltorio de la API OpenAI + validación de respuestas
│   └── prompts.py        # Plantillas de prompts
└── data/
    ├── player_state.json
    └── world_state.json
```

## Filosofía de diseño

**La IA describe. Python decide.**

| Lo que hace la IA ✓ | Lo que la IA NUNCA hace ✗ |
|---|---|
| Descripciones de escena | Modificar PV o estadísticas |
| Diálogo de PNJ | Tirar dados o calcular daño |
| Atmósfera y lore | Otorgar o quitar objetos |
| Señalar desencadenantes de combate | Decidir resultados de combate |
| Sugerir actualizaciones de misiones | Cambiar cantidades de oro |

## Configuración

```bash
pip install openai
setx OPENAI_API_KEY "sk-your-key-here"
python main.py
```
tambien se puede cambiar directamente desde el archivo main.py

Nuevo juego:
```bash
python main.py --new
```

## Comandos en el juego

| Comando | Descripción |
|---|---|
| Texto libre cualquiera | Tu acción (enviada a la IA) |
| `inventory` / `inv` | Mostrar objetos y oro |
| `status` / `stats` | Mostrar estadísticas del jugador |
| `memory` / `journal` | Mostrar la crónica |
| `world` / `location` | Mostrar información del mundo |
| `help` | Mostrar esta lista |
| `quit` / `exit` | Guardar y salir |

## Combate

El combate es completamente determinista:
- **Tirada D20** determina acierto/fallo
- **Daño** = resultado de la tirada + modificador de fuerza  
- **Crítico** en 20 natural (daño doble)
- **Probabilidad de huir** = 40% + (inteligencia × 2%)
- El enemigo contraataca cada ronda

## Sistema de memoria

Cada 5 turnos, la IA comprime registros de eventos en un párrafo vívido de la crónica. Esto mantiene el contexto ligero a la vez que preserva la continuidad narrativa en sesiones largas.

## Extender el juego

**Agregar un nuevo enemigo** — editar `game/combat.py`:
```python
ENEMY_TEMPLATES["dragon"] = make_enemy(
    "Dragón Ancestral", hp=80, attack=12, defense=15,
    xp_reward=500, gold_reward=200, loot=["Escama de Dragón"]
)
```
