"""
memory.py — Event memory and AI-powered summarization.

Events are appended each turn. Every SUMMARIZE_EVERY turns, the oldest
unsummarized events are compressed into a single AI-generated summary.
This keeps the context window lean without losing narrative continuity.

Architecture note: This module *does* call the AI, but only to summarize
past events — never to make game decisions. The summary is purely narrative.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

MEMORY_PATH = Path(__file__).parent.parent / "data" / "memory.json"
SUMMARIZE_EVERY = 5    # compress after every N events


class MemorySystem:
    """
    Maintains a rolling log of important game events.

    Structure:
      - events:   raw recent events (list of strings)
      - summaries: compressed AI summaries of older events
    """

    def __init__(
        self,
        events: Optional[list[str]] = None,
        summaries: Optional[list[str]] = None,
    ) -> None:
        self.events: list[str] = events or []
        self.summaries: list[str] = summaries or []

    # ── Public API ────────────────────────────────────────────────────────────

    def record(self, event: str) -> None:
        """Append a notable event to the live log."""
        self.events.append(event)

    def should_summarize(self) -> bool:
        """True when we've accumulated enough events to warrant a compression."""
        return len(self.events) >= SUMMARIZE_EVERY

    def summarize(self, openai_client) -> str:
        """
        Use the AI to compress current events into one summary paragraph,
        then reset the events list. Returns the summary string.

        This is the ONLY AI call made from this module, and it's strictly
        for narrative compression — no game decisions are made here.
        """
        if not self.events:
            return ""

        events_text = "\n".join(f"- {e}" for e in self.events)
        prompt = (
            "You are a dark fantasy chronicle keeper. Compress the following game events "
            "into a single vivid paragraph of 2-4 sentences, written in past tense, "
            "from the perspective of an omniscient narrator. Preserve all important "
            "facts (names, items, outcomes). Be atmospheric but concise.\n\n"
            f"Events:\n{events_text}"
        )

        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.7,
            )
            summary = response.choices[0].message.content.strip()
        except Exception as exc:
            # Graceful degradation: if AI call fails, join events as plain text
            summary = f"[Summary unavailable: {exc}] Raw events: {'; '.join(self.events)}"

        self.summaries.append(summary)
        self.events.clear()
        return summary

    def get_context_block(self) -> str:
        """
        Return a formatted memory block suitable for insertion into
        the AI dungeon master's system prompt.
        """
        parts: list[str] = []

        if self.summaries:
            parts.append("=== Chronicle of Past Events ===")
            for i, s in enumerate(self.summaries, 1):
                parts.append(f"[Chapter {i}] {s}")

        if self.events:
            parts.append("=== Recent Events ===")
            for e in self.events:
                parts.append(f"• {e}")

        return "\n".join(parts) if parts else "No significant events recorded yet."

    # ── Persistence ───────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {"events": self.events, "summaries": self.summaries}

    def save(self, path: Path = MEMORY_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path = MEMORY_PATH) -> "MemorySystem":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        return cls(**data)

    def __repr__(self) -> str:
        return (
            f"MemorySystem(events={len(self.events)}, "
            f"summaries={len(self.summaries)})"
        )
