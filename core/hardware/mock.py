from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncIterator

from ..types import AudioResult, CaptureResult, WakeEvent
from .base import HardwareInterface

DEFAULT_CAPS: set[str] = {
    "camera", "mic", "speaker", "wake", "face", "voiceprint", "bt", "music",
}


class MockHardware(HardwareInterface):
    """Deterministic HAL backed by a fixture directory. Used by the eval harness.

    Fixture layout::

        fixtures/<scenario>/
          scenario.json    # {transcript, owner_face, owner_voice, voice_score,
                           #  wake_events: [{persona, confidence, ts}]}
          capture.png      # bytes returned by capture_image
          record.wav       # bytes returned by record_audio

    `spoken`, `music_queries`, `music_playing` are exposed for assertions in
    test cases.
    """

    def __init__(
        self,
        fixtures_dir: Path,
        capabilities: set[str] | None = None,
    ) -> None:
        self.fixtures = Path(fixtures_dir)
        self.spoken: list[bytes] = []
        self.music_queries: list[str] = []
        self.music_playing: bool = False
        self.scenario: dict = self._load_scenario()
        self._caps: set[str] = set(capabilities) if capabilities is not None else set(DEFAULT_CAPS)

    def _load_scenario(self) -> dict:
        f = self.fixtures / "scenario.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
        return {}

    @property
    def capabilities(self) -> set[str]:
        return self._caps

    async def capture_image(self) -> CaptureResult:
        f = self.fixtures / "capture.png"
        if not f.exists():
            return CaptureResult(image_bytes=None, width=0, height=0, error="no fixture")
        return CaptureResult(image_bytes=f.read_bytes(), width=640, height=480, error=None)

    async def record_audio(self, duration_s: float) -> AudioResult:
        f = self.fixtures / "record.wav"
        transcript = self.scenario.get("transcript")
        audio = f.read_bytes() if f.exists() else None
        return AudioResult(audio_bytes=audio, transcript=transcript, duration_s=duration_s, error=None)

    async def speak(self, audio_chunks: AsyncIterator[bytes]) -> None:
        async for chunk in audio_chunks:
            self.spoken.append(chunk)

    async def play_music(self, query: str) -> None:
        self.music_queries.append(query)
        self.music_playing = True

    async def stop_music(self) -> None:
        self.music_playing = False

    async def _gen_wake(self) -> AsyncIterator[WakeEvent]:
        for ev in self.scenario.get("wake_events", []):
            await asyncio.sleep(0)
            yield WakeEvent(
                persona=ev["persona"],
                confidence=float(ev.get("confidence", 1.0)),
                ts=float(ev.get("ts", 0.0)),
            )

    def stream_wake_events(self) -> AsyncIterator[WakeEvent]:
        return self._gen_wake()

    async def detect_owner_face(self) -> bool:
        return bool(self.scenario.get("owner_face", True))

    async def verify_speaker(self, audio: bytes) -> tuple[bool, float]:
        return (
            bool(self.scenario.get("owner_voice", True)),
            float(self.scenario.get("voice_score", 0.9)),
        )

    async def duck_music(self, db: float, ms: int) -> None:
        return None
