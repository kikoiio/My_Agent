from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from ..types import AudioResult, CaptureResult, WakeEvent


class HardwareInterface(ABC):
    """Hardware abstraction layer (HAL).

    Four implementations exist:
      - RPiHardware: real Pi (picamera2, openWakeWord, sherpa-onnx, ...).
      - RemoteHardware: Pi audio/video proxied to backend over Pipecat WS.
      - MockHardware: fixture-backed, deterministic, used by eval harness.
      - NullHardware: degraded fallback; capabilities=set().

    Tools annotated with `requires_capability=...` are filtered out of the
    LLM-visible tool set when the active HAL lacks the capability.
    """

    @property
    @abstractmethod
    def capabilities(self) -> set[str]:
        """e.g. {"camera", "mic", "speaker", "wake", "face", "voiceprint", "bt", "music"}."""

    @abstractmethod
    async def capture_image(self) -> CaptureResult: ...

    @abstractmethod
    async def record_audio(self, duration_s: float) -> AudioResult: ...

    @abstractmethod
    async def speak(self, audio_chunks: AsyncIterator[bytes]) -> None: ...

    @abstractmethod
    async def play_music(self, query: str) -> None: ...

    @abstractmethod
    async def stop_music(self) -> None: ...

    @abstractmethod
    def stream_wake_events(self) -> AsyncIterator[WakeEvent]:
        """Returns an async iterator of WakeEvent. Implementations are typically
        async generators (`async def` + `yield`); calling this method must NOT
        await — it must return an iterator object directly."""

    @abstractmethod
    async def detect_owner_face(self) -> bool: ...

    @abstractmethod
    async def verify_speaker(self, audio: bytes) -> tuple[bool, float]: ...

    @abstractmethod
    async def duck_music(self, db: float, ms: int) -> None: ...
