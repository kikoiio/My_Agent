"""Piper TTS fallback (lightweight, offline).

Plan.md §9.1: Piper for offline fallback when cloud TTS unavailable.
"""

from __future__ import annotations

import asyncio
from typing import Any

__all__ = ["PiperClient"]


class PiperClient:
    """Piper offline TTS (fallback)."""

    def __init__(
        self,
        model_path: str | None = None,
        language: str = "zh-cn",
    ):
        """Initialize Piper client.

        Args:
            model_path: Path to Piper model file (.onnx)
            language: Language code (e.g., "zh-cn", "en-us")
        """
        self.model_path = model_path
        self.language = language
        self.available = model_path is not None

    async def synthesize(
        self,
        text: str,
        speaker: str = "default",
        rate: float = 1.0,
    ) -> bytes:
        """Synthesize text offline using Piper.

        Args:
            text: Text to synthesize
            speaker: Speaker ID
            rate: Speech rate multiplier

        Returns:
            Audio bytes (wav)
        """
        if not self.available:
            raise RuntimeError("Piper model not loaded")

        # Placeholder: would use piper-tts library
        # Would load model and run inference
        await asyncio.sleep(0.5)  # Simulate inference time
        return b"WAV_AUDIO_PLACEHOLDER"

    async def list_available_models(self) -> list[str]:
        """List available Piper models."""
        return [
            "en_US-lessac-medium",
            "zh_CN-huayan-medium",
            "zh_CN-male_c-medium",
            "zh_CN-muxing_c-medium",
        ]

    async def preload_model(self, model_name: str) -> bool:
        """Preload model for faster synthesis.

        Args:
            model_name: Model name to preload

        Returns:
            True if successful
        """
        # Placeholder
        self.available = True
        return True

    def is_available(self) -> bool:
        """Check if Piper is available."""
        return self.available

    async def get_sample_rate(self) -> int:
        """Get sample rate of current model."""
        return 22050
