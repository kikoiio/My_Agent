"""CosyVoice TTS client with DashScope API and self-hosted fallover.

Plan.md §9.1: Primary uses Aliyun DashScope API, falls back to self-hosted server.
"""

from __future__ import annotations

import asyncio
from typing import Any

__all__ = ["CosyVoiceClient"]


class CosyVoiceClient:
    """CosyVoice TTS with multi-endpoint fallover."""

    def __init__(
        self,
        dashscope_api_key: str | None = None,
        dashscope_model: str = "cosyvoice-v1",
        self_hosted_url: str | None = None,
        voice_id: str = "longhui",
    ):
        """Initialize CosyVoice client.

        Args:
            dashscope_api_key: Aliyun DashScope API key
            dashscope_model: Model ID (default: cosyvoice-v1)
            self_hosted_url: Optional self-hosted server URL (e.g., http://localhost:8000)
            voice_id: Voice ID to use (e.g., "longhui", "xiaoxiao")
        """
        self.dashscope_api_key = dashscope_api_key
        self.dashscope_model = dashscope_model
        self.self_hosted_url = self_hosted_url
        self.voice_id = voice_id
        self.available = dashscope_api_key is not None or self_hosted_url is not None

    async def synthesize(self, text: str) -> bytes:
        """Synthesize text to speech.

        Args:
            text: Text to synthesize

        Returns:
            Audio bytes (wav/mp3)
        """
        # Try DashScope first
        if self.dashscope_api_key:
            try:
                audio_bytes = await self._synthesize_dashscope(text)
                return audio_bytes
            except Exception as e:
                print(f"DashScope synthesis failed: {e}, falling back to self-hosted")

        # Fall back to self-hosted
        if self.self_hosted_url:
            try:
                audio_bytes = await self._synthesize_self_hosted(text)
                return audio_bytes
            except Exception as e:
                print(f"Self-hosted synthesis failed: {e}")

        # No available endpoint
        raise RuntimeError(
            "No available TTS endpoint (DashScope disabled and no self-hosted configured)"
        )

    async def _synthesize_dashscope(self, text: str) -> bytes:
        """Call DashScope API (requires dashscope package)."""
        # Placeholder: would call actual DashScope API
        # In real usage, would use: dashscope.TextToSpeech.call(...)
        await asyncio.sleep(0.1)  # Simulate network latency
        return b"PCM_AUDIO_PLACEHOLDER"

    async def _synthesize_self_hosted(self, text: str) -> bytes:
        """Call self-hosted CosyVoice server."""
        # Placeholder: would make HTTP request to self-hosted server
        # POST to {self_hosted_url}/synthesize with {text, voice_id}
        await asyncio.sleep(0.1)  # Simulate network latency
        return b"PCM_AUDIO_PLACEHOLDER"

    async def get_voices(self) -> list[str]:
        """Get available voice IDs."""
        return [
            "longhui",
            "xiaoxiao",
            "xiaowei",
            "yunjian",
            "yunxi",
            "yunyang",
        ]

    def is_available(self) -> bool:
        """Check if any TTS endpoint is configured."""
        return self.available
