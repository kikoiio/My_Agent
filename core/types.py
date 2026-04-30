from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


@dataclass(slots=True)
class CaptureResult:
    image_bytes: bytes | None
    width: int
    height: int
    error: str | None = None


@dataclass(slots=True)
class AudioResult:
    audio_bytes: bytes | None
    transcript: str | None
    duration_s: float
    error: str | None = None


@dataclass(slots=True)
class WakeEvent:
    persona: str
    confidence: float
    ts: float


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None
    tool_call_id: str | None = None


@dataclass(slots=True)
class EmotionContext:
    persona: str
    valence: float   # -1.0 (negative) → 1.0 (positive)
    arousal: float   # 0.0 (calm) → 1.0 (excited)
    tone: str        # "neutral" | "happy" | "sad" | "anxious" | "excited"
    ts: float = field(default_factory=time.time)


@dataclass(slots=True)
class ProactiveEvent:
    trigger: str    # "emotion_trend" | "topic_followup" | "home_arrival"
    persona: str
    user_id: str
    message: str    # ready-to-speak opening line
    priority: int = 1   # 1=low, 2=medium, 3=high
    ts: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


class AgentState(BaseModel):
    """Per-turn state passed through the LangGraph main graph.

    `role` selects the routing class (chat / dream / memory_writer); the
    semantic-memory writer and the Dream worker share the cheap-LLM lane.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: str = "owner"
    persona: str
    active_persona_id: str = ""  # persona 目录名，用于 L2 记忆路由
    messages: list[Message] = Field(default_factory=list)
    role: Literal["chat", "dream", "memory_writer"] = "chat"
    has_image: bool = False
    is_long_context_consolidation: bool = False
    tools_called: list[str] = Field(default_factory=list)
    trace_id: str | None = None
