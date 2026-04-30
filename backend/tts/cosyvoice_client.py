"""CosyVoice TTS client with DashScope API and self-hosted fallover.

Plan.md §9.1: Primary uses Aliyun DashScope API, falls back to self-hosted server.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

__all__ = ["CosyVoiceClient"]

logger = logging.getLogger(__name__)


class CosyVoiceClient:
    """CosyVoice TTS with multi-endpoint fallover."""

    def __init__(
        self,
        dashscope_api_key: str | None = None,
        dashscope_model: str = "cosyvoice-v1",
        self_hosted_url: str | None = None,
        voice_id: str = "longhui",
    ):
        self.dashscope_api_key = dashscope_api_key
        self.dashscope_model = dashscope_model
        self.self_hosted_url = self_hosted_url
        self.voice_id = voice_id
        self.available = dashscope_api_key is not None or self_hosted_url is not None

    async def synthesize(self, text: str, voice_ref: str | None = None) -> bytes:
        """Synthesize text to speech, returns PCM/wav bytes.

        Args:
            text: Text to synthesize.
            voice_ref: Path to a .wav reference file for zero-shot voice cloning.
                       When provided, the self-hosted endpoint is used with the
                       reference audio.  Falls back to the standard voice_id when
                       voice_ref is None or the file is missing.
        """
        if voice_ref and self.self_hosted_url:
            try:
                return await self._synthesize_zero_shot(text, voice_ref)
            except Exception as e:
                logger.warning(f"Zero-shot synthesis failed: {e!r}, falling back to default voice")

        if self.dashscope_api_key:
            try:
                return await self._synthesize_dashscope(text)
            except Exception as e:
                logger.warning(f"DashScope synthesis failed: {e!r}, trying self-hosted")

        if self.self_hosted_url:
            try:
                return await self._synthesize_self_hosted(text)
            except Exception as e:
                logger.warning(f"Self-hosted synthesis failed: {e!r}")

        raise RuntimeError(
            "No available TTS endpoint (DashScope disabled and no self-hosted configured)"
        )

    async def _synthesize_dashscope(self, text: str) -> bytes:
        """Call Aliyun DashScope CosyVoice API."""
        try:
            from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer
        except ImportError as exc:
            raise RuntimeError("dashscope package not installed") from exc

        import dashscope
        dashscope.api_key = self.dashscope_api_key  # type: ignore[attr-defined]

        synthesizer = SpeechSynthesizer(
            model=self.dashscope_model,
            voice=self.voice_id,
            format=AudioFormat.PCM_22050HZ_MONO_16BIT,
        )
        result = synthesizer.call(text)
        audio: bytes | None = result.get_audio_data()
        if not audio:
            raise RuntimeError(
                f"DashScope TTS returned empty audio; status={getattr(result, 'status_code', '?')}"
                f" message={getattr(result, 'message', '')}"
            )
        return audio

    async def _synthesize_self_hosted(self, text: str) -> bytes:
        """Call self-hosted CosyVoice inference server.

        Expects: POST {self_hosted_url}/v1/inference_sft
        Body: {"tts_text": text, "spk_id": voice_id, "stream": false}
        Response: binary PCM/wav bytes
        """
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.self_hosted_url}/v1/inference_sft",
                json={"tts_text": text, "spk_id": self.voice_id, "stream": False},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                return await resp.read()

    async def _synthesize_zero_shot(self, text: str, voice_ref: str) -> bytes:
        """Zero-shot voice clone via self-hosted CosyVoice server.

        Expects: POST {self_hosted_url}/v1/inference_zero_shot
        Body: multipart/form-data with tts_text + prompt_wav file
        """
        import aiohttp
        from pathlib import Path

        ref_path = Path(voice_ref)
        if not ref_path.exists():
            raise FileNotFoundError(f"voice_ref not found: {voice_ref}")

        audio_bytes = ref_path.read_bytes()
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field("tts_text", text)
            form.add_field(
                "prompt_wav",
                audio_bytes,
                filename=ref_path.name,
                content_type="audio/wav",
            )
            async with session.post(
                f"{self.self_hosted_url}/v1/inference_zero_shot",
                data=form,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                resp.raise_for_status()
                return await resp.read()

    async def synthesize_stream(
        self, text: str, voice_ref: str | None = None
    ) -> AsyncGenerator[bytes, None]:
        """Streaming TTS variant — yields audio chunks as they become available.

        Uses chunked HTTP streaming when the self-hosted server supports it
        (POST /v1/inference_sft_stream).  Falls back to synthesize() and yields
        the whole audio as a single chunk so callers always get an async generator.
        """
        if self.self_hosted_url:
            try:
                async for chunk in self._stream_self_hosted(text, voice_ref):
                    yield chunk
                return
            except Exception as e:
                logger.warning(f"Streaming TTS failed: {e!r}, falling back to full synthesis")

        # Fallback: full synthesis, yield as single chunk
        audio = await self.synthesize(text, voice_ref)
        yield audio

    async def _stream_self_hosted(
        self, text: str, voice_ref: str | None
    ) -> AsyncGenerator[bytes, None]:
        """Chunked streaming from self-hosted CosyVoice server.

        Tries /v1/inference_sft_stream (Transfer-Encoding: chunked).
        Falls back to zero-shot endpoint when voice_ref is provided.
        """
        import aiohttp

        if voice_ref:
            # Zero-shot streaming not universally supported; delegate to full call
            audio = await self._synthesize_zero_shot(text, voice_ref)
            yield audio
            return

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.self_hosted_url}/v1/inference_sft_stream",
                json={"tts_text": text, "spk_id": self.voice_id, "stream": True},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                resp.raise_for_status()
                async for chunk, _ in resp.content.iter_chunks():
                    if chunk:
                        yield chunk

    async def get_voices(self) -> list[str]:
        return ["longhui", "xiaoxiao", "xiaowei", "yunjian", "yunxi", "yunyang"]

    def is_available(self) -> bool:
        return self.available
