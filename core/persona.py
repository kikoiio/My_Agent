from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(slots=True)
class Persona:
    name: str
    system_prompt: str
    voice_ref_path: Path
    voice_ref_text: str
    wake_model_path: Path | None
    tools_allowed: list[str] = field(default_factory=list)
    tools_denied: list[str] = field(default_factory=list)
    require_speaker_verify: list[str] = field(default_factory=list)
    memory_init: dict = field(default_factory=dict)
    routing: dict = field(default_factory=dict)


def load(persona_dir: Path) -> Persona:
    persona_dir = Path(persona_dir)
    if not persona_dir.is_dir():
        raise FileNotFoundError(f"persona dir missing: {persona_dir}")

    name = persona_dir.name
    sp_path = persona_dir / "system_prompt.md"
    if not sp_path.exists():
        raise FileNotFoundError(f"{name}: system_prompt.md required")
    system_prompt = sp_path.read_text(encoding="utf-8")

    voice_ref = persona_dir / "voice_ref.wav"
    vr_txt = persona_dir / "voice_ref.txt"
    voice_ref_text = vr_txt.read_text(encoding="utf-8").strip() if vr_txt.exists() else ""

    wake = persona_dir / "wake.onnx"

    tools_yaml = persona_dir / "tools.yaml"
    tools_data: dict = {}
    if tools_yaml.exists():
        tools_data = yaml.safe_load(tools_yaml.read_text(encoding="utf-8")) or {}

    init_json = persona_dir / "memory_init.json"
    memory_init = json.loads(init_json.read_text(encoding="utf-8")) if init_json.exists() else {}

    routing_yaml = persona_dir / "routing.yaml"
    routing: dict = {}
    if routing_yaml.exists():
        routing = yaml.safe_load(routing_yaml.read_text(encoding="utf-8")) or {}

    return Persona(
        name=name,
        system_prompt=system_prompt,
        voice_ref_path=voice_ref,
        voice_ref_text=voice_ref_text,
        wake_model_path=wake if wake.exists() else None,
        tools_allowed=list(tools_data.get("allowed") or []),
        tools_denied=list(tools_data.get("denied") or []),
        require_speaker_verify=list(tools_data.get("require_speaker_verify") or []),
        memory_init=memory_init,
        routing=routing,
    )


def list_personas(personas_root: Path) -> list[str]:
    root = Path(personas_root)
    if not root.is_dir():
        return []
    return sorted(
        d.name
        for d in root.iterdir()
        if d.is_dir() and not d.name.startswith("_") and not d.name.startswith(".")
    )
