"""Acoustic emotion feature extraction — placeholder implementation.

Plan.md P3: EmotionExtractor analyses raw audio bytes and returns an
EmotionContext. The real implementation would use a librosa/openSMILE
feature pipeline plus a lightweight classifier. This stub returns a
neutral context so the rest of the pipeline can be tested without hardware.
"""

from __future__ import annotations

import time

from core.types import EmotionContext

__all__ = ["EmotionExtractor"]

_VALID_TONES = {"neutral", "happy", "sad", "anxious", "excited"}


class EmotionExtractor:
    """Acoustic emotion feature extractor (stub)."""

    def __init__(self, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate

    async def extract(self, audio_chunk: bytes) -> EmotionContext:
        """Extract emotion from a raw PCM audio chunk.

        Returns neutral context until a real model is wired in.
        """
        return EmotionContext(
            persona="",
            valence=0.0,
            arousal=0.5,
            tone="neutral",
            ts=time.time(),
        )

    async def extract_stream(self, audio_stream) -> EmotionContext:
        """Consume an audio stream and return an aggregate EmotionContext."""
        chunks: list[bytes] = []
        async for chunk in audio_stream:
            chunks.append(chunk)
        combined = b"".join(chunks)
        return await self.extract(combined)
