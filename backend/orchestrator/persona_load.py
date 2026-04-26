"""Persona loading and injection into graph state.

Per plan.md §10.2: Load persona metadata and prepare for graph execution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.persona import Persona, load

__all__ = ["load_persona_into_graph", "PersonaGraphAdapter"]


def load_persona_into_graph(
    persona_path: Path | str,
    graph_state: Any,
) -> dict[str, Any]:
    """Load persona from disk and inject into graph state.

    Args:
        persona_path: Path to persona directory
        graph_state: Graph state object

    Returns:
        Updated graph state dict
    """
    # Load persona
    persona = load(persona_path)

    # Inject into state
    if hasattr(graph_state, "persona"):
        graph_state.persona = persona.name
    if hasattr(graph_state, "system_prompt"):
        graph_state.system_prompt = persona.system_prompt

    return {
        "persona": persona,
        "system_prompt": persona.system_prompt,
        "voice_ref_path": str(persona.voice_ref_path),
        "voice_ref_text": persona.voice_ref_text,
        "tools_allowed": persona.tools_allowed,
        "tools_denied": persona.tools_denied,
    }


class PersonaGraphAdapter:
    """Adapter to load persona context into LangGraph state."""

    def __init__(self, personas_root: Path | str = "personas"):
        """Initialize adapter.

        Args:
            personas_root: Root directory containing persona subdirs
        """
        self.personas_root = Path(personas_root)

    async def inject_persona(
        self,
        persona_name: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """Inject persona metadata into graph state.

        Args:
            persona_name: Name of persona to load
            state: Graph state dict

        Returns:
            Updated state
        """
        persona_path = self.personas_root / persona_name

        if not persona_path.exists():
            raise FileNotFoundError(f"Persona not found: {persona_name}")

        try:
            persona = load(persona_path)
        except Exception as e:
            raise RuntimeError(f"Failed to load persona {persona_name}: {e}")

        # Update state with persona data
        state.update(
            {
                "persona_name": persona.name,
                "system_prompt": persona.system_prompt,
                "voice_ref_text": persona.voice_ref_text,
                "wake_model_path": str(persona.wake_model_path) if persona.wake_model_path else None,
                "tools_allowed": persona.tools_allowed,
                "tools_denied": persona.tools_denied,
                "memory_init": persona.memory_init,
                "routing": persona.routing,
            }
        )

        return state

    def get_system_prompt(self, persona_name: str) -> str:
        """Get system prompt for a persona.

        Args:
            persona_name: Persona name

        Returns:
            System prompt text
        """
        persona_path = self.personas_root / persona_name
        persona = load(persona_path)
        return persona.system_prompt

    def get_tools_for_persona(self, persona_name: str) -> dict[str, list[str]]:
        """Get tool restrictions for a persona.

        Args:
            persona_name: Persona name

        Returns:
            Dict with 'allowed' and 'denied' lists
        """
        persona_path = self.personas_root / persona_name
        persona = load(persona_path)
        return {
            "allowed": persona.tools_allowed,
            "denied": persona.tools_denied,
            "require_speaker_verify": persona.require_speaker_verify,
        }
