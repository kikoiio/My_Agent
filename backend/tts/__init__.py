"""Text-to-speech clients with failover strategy.

Public helpers:
    play_audio_mp3(mp3_bytes)          — decode MP3 and play via sounddevice
    play_audio_streaming(audio_gen)    — stream MP3 chunks, decode, play
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

__all__ = ["play_audio_mp3", "play_audio_streaming"]

logger = logging.getLogger(__name__)


async def play_audio_mp3(mp3_bytes: bytes, *, blocking: bool = True) -> None:
    """Decode MP3 bytes and play through the default audio output device.

    Uses ``miniaudio`` for decoding and ``sounddevice`` for playback.
    Falls back to writing a temp file and opening it with the OS player
    when either library is unavailable.

    Args:
        mp3_bytes: Raw MP3 audio data.
        blocking: If True, wait until playback finishes before returning.
    """
    if not mp3_bytes:
        return

    try:
        _play_with_miniaudio(mp3_bytes, blocking=blocking)
    except ImportError:
        logger.debug("miniaudio/sounddevice not available; using OS fallback")
        await _play_os_fallback(mp3_bytes)
    except Exception as exc:
        logger.warning("Audio playback failed: %r; trying OS fallback", exc)
        await _play_os_fallback(mp3_bytes)


async def play_audio_streaming(
    audio_gen: AsyncGenerator[bytes, None], *, chunk_buffer: int = 4
) -> None:
    """Collect streaming MP3 chunks, then play the assembled audio.

    Args:
        audio_gen: Async generator yielding MP3 byte chunks.
        chunk_buffer: Unused — kept for API stability.
    """
    import io
    buf = io.BytesIO()
    async for chunk in audio_gen:
        if chunk:
            buf.write(chunk)
    mp3_bytes = buf.getvalue()
    if mp3_bytes:
        await play_audio_mp3(mp3_bytes)


def _play_with_miniaudio(mp3_bytes: bytes, *, blocking: bool) -> None:
    """Decode with miniaudio → play with sounddevice (synchronous)."""
    import miniaudio
    import sounddevice as sd
    import numpy as np

    decoded = miniaudio.decode(
        mp3_bytes,
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=24000,
    )
    samples = np.frombuffer(decoded.samples, dtype=np.int16).astype(np.float32) / 32768.0
    sd.play(samples, samplerate=decoded.sample_rate)
    if blocking:
        sd.wait()


async def _play_os_fallback(mp3_bytes: bytes) -> None:
    """Write MP3 to a temp file and open with the OS default player."""
    import tempfile
    import subprocess
    import sys

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(mp3_bytes)
        tmp_path = f.name

    try:
        if sys.platform == "win32":
            await asyncio.to_thread(
                subprocess.run,
                ["powershell", "-c", f"(New-Object Media.SoundPlayer '{tmp_path}').PlaySync()"],
                check=False,
            )
        elif sys.platform == "darwin":
            await asyncio.to_thread(subprocess.run, ["afplay", tmp_path], check=False)
        else:
            await asyncio.to_thread(subprocess.run, ["aplay", tmp_path], check=False)
    finally:
        import os
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
