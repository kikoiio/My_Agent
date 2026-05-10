"""Text-to-speech clients with failover strategy.

Public helpers:
    play_audio_mp3(mp3_bytes)          — decode MP3 and play via sounddevice
    play_audio_streaming(audio_gen)    — stream MP3 chunks, decode, play
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

__all__ = ["play_audio_mp3", "play_audio_streaming", "_find_output_device"]

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


def _find_output_device() -> int | None:
    """Return output device ID, or None for the OS default.

    Reads VOICE_OUTPUT_DEVICE from the environment:
    - Integer string → use that device index directly
    - Non-integer string → case-insensitive substring match on device name
    - Unset / empty → return None (PortAudio OS default)

    Example:
        $env:VOICE_OUTPUT_DEVICE = "Philips"   # match by name
        $env:VOICE_OUTPUT_DEVICE = "3"         # use device index 3
    """
    import os
    import sounddevice as sd

    spec = os.environ.get("VOICE_OUTPUT_DEVICE", "").strip()
    if not spec:
        return None
    try:
        idx = int(spec)
        logger.debug("Using output device index %d (VOICE_OUTPUT_DEVICE)", idx)
        return idx
    except ValueError:
        pass
    spec_lower = spec.lower()
    try:
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            if d.get("max_output_channels", 0) > 0 and spec_lower in d.get("name", "").lower():
                logger.info("Output device [%d]: %s", i, d["name"])
                return i
    except Exception:
        pass
    logger.warning("VOICE_OUTPUT_DEVICE=%r not found; using OS default", spec)
    return None


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
    output_device = _find_output_device()
    sd.play(samples, samplerate=decoded.sample_rate, device=output_device)
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
