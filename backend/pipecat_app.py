"""Pipecat pipeline for real-time audio I/O.

Per plan.md §10.1:
- STT (Speech-to-Text) → LLM (LangGraph brain) → TTS (Text-to-Speech)
- WebSocket transport for Pi ↔ Backend communication
"""

from __future__ import annotations

from typing import Any, Callable

__all__ = ["PipecatPipeline"]


class PipecatPipeline:
    """Real-time audio pipeline for Pipecat."""

    def __init__(
        self,
        stt_engine: Any,  # STT provider
        llm_handler: Callable[[str], str],  # LLM callback
        tts_engine: Any,  # TTS provider
        sample_rate: int = 16000,
        channels: int = 1,
    ):
        """Initialize Pipecat pipeline.

        Args:
            stt_engine: STT provider (e.g., Sherpa, OpenAI Whisper)
            llm_handler: Async callback for LLM processing
            tts_engine: TTS provider (e.g., CosyVoice, Fish-Speech)
            sample_rate: Audio sample rate (Hz)
            channels: Number of audio channels
        """
        self.stt_engine = stt_engine
        self.llm_handler = llm_handler
        self.tts_engine = tts_engine
        self.sample_rate = sample_rate
        self.channels = channels

    async def process_audio_frame(self, audio_bytes: bytes) -> tuple[str, bytes]:
        """Process single audio frame through pipeline.

        Args:
            audio_bytes: Raw audio bytes

        Returns:
            (transcript, response_audio_bytes)
        """
        # STT: Convert audio to text
        transcript = await self._stt(audio_bytes)
        if not transcript:
            return "", b""

        # LLM: Get response
        response_text = await self.llm_handler(transcript)
        if not response_text:
            return transcript, b""

        # TTS: Convert text to audio
        response_audio = await self._tts(response_text)

        return transcript, response_audio

    async def _stt(self, audio_bytes: bytes) -> str:
        """Speech-to-text conversion."""
        # Placeholder: would call actual STT engine
        # In real usage: sherpa-onnx, OpenAI Whisper, etc.
        return "Transcribed text from audio"

    async def _tts(self, text: str) -> bytes:
        """Text-to-speech conversion."""
        # Placeholder: would call TTS engine
        # Returns audio bytes
        return b"PCM_AUDIO_RESPONSE"

    async def stream_audio(
        self,
        audio_source: Any,  # AsyncIterator[bytes]
        on_text: Callable[[str], None] | None = None,
        on_audio: Callable[[bytes], None] | None = None,
    ) -> None:
        """Stream audio through pipeline.

        Args:
            audio_source: Async iterator of audio frames
            on_text: Callback for transcription results
            on_audio: Callback for response audio
        """
        async for audio_frame in audio_source:
            transcript, response_audio = await self.process_audio_frame(audio_frame)

            if on_text and transcript:
                on_text(transcript)

            if on_audio and response_audio:
                on_audio(response_audio)

    async def setup(self) -> None:
        """Initialize pipeline components."""
        # Load models, connect to services, etc.
        pass

    async def shutdown(self) -> None:
        """Clean up pipeline resources."""
        pass
