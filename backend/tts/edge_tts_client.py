"""edge-tts TTS client — free Microsoft TTS with high-quality Chinese voices.

No API key required. Requires internet access (calls Microsoft Edge TTS service).
Default voice: zh-CN-XiaoxiaoNeural (female, natural Chinese).

Fallback chain in CosyVoiceClient: self_hosted → dashscope → EdgeTTS → dummy.
"""

from __future__ import annotations

import io
import logging
from typing import AsyncGenerator

__all__ = ["EdgeTTSClient", "CHINESE_VOICES"]

logger = logging.getLogger(__name__)

CHINESE_VOICES = [
    "zh-CN-XiaoxiaoNeural",   # female, warm, natural
    "zh-CN-YunxiNeural",      # male, energetic
    "zh-CN-XiaohanNeural",    # female, calm
    "zh-CN-YunjianNeural",    # male, calm
    "zh-CN-XiaoyiNeural",     # female, lively
    "zh-TW-HsiaoChenNeural",  # Taiwan Mandarin female
]


class EdgeTTSClient:
    """Microsoft Edge TTS — free, no API key, excellent Chinese support."""

    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural", rate: str = "+0%", volume: str = "+0%"):
        self.voice = voice
        self.rate = rate
        self.volume = volume

    def is_available(self) -> bool:
        try:
            import edge_tts  # noqa: F401
            return True
        except ImportError:
            return False

    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        """Synthesize text → full MP3 bytes.

        Args:
            text: Text to speak.
            voice: Optional voice override (uses self.voice if None).

        Returns:
            MP3 audio bytes. Raises RuntimeError if edge_tts not installed.
        """
        try:
            import edge_tts
        except ImportError as exc:
            raise RuntimeError("edge-tts not installed: pip install edge-tts") from exc

        buf = io.BytesIO()
        communicate = edge_tts.Communicate(text, voice or self.voice, rate=self.rate, volume=self.volume)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        audio = buf.getvalue()
        if not audio:
            raise RuntimeError(f"edge-tts returned empty audio for text: {text[:50]!r}")
        return audio

    async def synthesize_stream(self, text: str, voice: str | None = None) -> AsyncGenerator[bytes, None]:
        """Yield MP3 chunks as they arrive from the service.

        Args:
            text: Text to speak.
            voice: Optional voice override.

        Yields:
            MP3 audio byte chunks.
        """
        try:
            import edge_tts
        except ImportError as exc:
            raise RuntimeError("edge-tts not installed: pip install edge-tts") from exc

        communicate = edge_tts.Communicate(text, voice or self.voice, rate=self.rate, volume=self.volume)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    async def list_voices(self, locale: str = "zh-CN") -> list[dict]:
        """List available voices for a locale.

        Args:
            locale: BCP-47 locale string (e.g. "zh-CN", "en-US").

        Returns:
            List of voice dicts with Name, Gender, Locale keys.
        """
        try:
            import edge_tts
        except ImportError:
            return []
        voices = await edge_tts.list_voices()
        return [v for v in voices if v.get("Locale", "").startswith(locale)]
