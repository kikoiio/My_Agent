from __future__ import annotations

from typing import AsyncIterator

from ..types import AudioResult, CaptureResult, WakeEvent
from .base import HardwareInterface


class NullHardware(HardwareInterface):
    """Degraded fallback. capabilities=set(); every method returns a soft no-op
    or 'unavailable' marker so the rest of the system stays alive when the real
    HAL is unreachable (e.g. backend lost contact with Pi)."""

    @property
    def capabilities(self) -> set[str]:
        return set()

    async def capture_image(self) -> CaptureResult:
        return CaptureResult(image_bytes=None, width=0, height=0, error="no hardware")

    async def record_audio(self, duration_s: float) -> AudioResult:
        return AudioResult(audio_bytes=None, transcript=None, duration_s=0.0, error="no hardware")

    async def speak(self, audio_chunks: AsyncIterator[bytes]) -> None:
        async for _ in audio_chunks:
            pass

    async def play_music(self, query: str) -> None:
        return None

    async def stop_music(self) -> None:
        return None

    async def _empty(self) -> AsyncIterator[WakeEvent]:
        if False:
            yield  # pragma: no cover

    def stream_wake_events(self) -> AsyncIterator[WakeEvent]:
        return self._empty()

    async def detect_owner_face(self) -> bool:
        return False

    async def verify_speaker(self, audio: bytes) -> tuple[bool, float]:
        return (False, 0.0)

    async def duck_music(self, db: float, ms: int) -> None:
        return None
