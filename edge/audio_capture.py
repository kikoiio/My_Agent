"""Microphone capture utilities using sounddevice.

Provides two capture modes:
  1. capture_fixed_duration()  — record exactly N seconds of audio
  2. capture_until_silence()   — record until the user stops speaking (energy VAD)
  3. stream_microphone()       — continuous async generator of raw PCM chunks

All audio is 16 kHz mono float32 unless otherwise noted.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

__all__ = [
    "SAMPLE_RATE",
    "capture_fixed_duration",
    "capture_until_silence",
    "stream_microphone",
]

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000  # Hz
_CHUNK_FRAMES = 1_600  # 100 ms per chunk at 16 kHz


async def capture_fixed_duration(seconds: float = 5.0) -> "numpy.ndarray":
    """Record a fixed duration of audio from the default microphone.

    Args:
        seconds: Duration in seconds.

    Returns:
        Float32 numpy array of shape (N,) at SAMPLE_RATE.

    Raises:
        RuntimeError: If sounddevice is not installed.
    """
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("sounddevice not installed: pip install sounddevice") from exc

    frames = int(seconds * SAMPLE_RATE)
    logger.debug("Capturing %.1f s of audio (%d frames)", seconds, frames)
    audio = await asyncio.to_thread(
        sd.rec, frames, samplerate=SAMPLE_RATE, channels=1, dtype="float32"
    )
    await asyncio.to_thread(sd.wait)
    return audio.flatten()


async def capture_until_silence(
    silence_threshold: float = 0.015,
    silence_duration: float = 1.5,
    max_duration: float = 10.0,
    pre_roll_ms: int = 200,
) -> "numpy.ndarray":
    """Record until the speaker stops talking (energy-based VAD).

    Starts buffering immediately.  Stops when RMS energy stays below
    ``silence_threshold`` for ``silence_duration`` seconds, or after
    ``max_duration`` seconds total.

    Args:
        silence_threshold: RMS energy threshold (0–1) for silence detection.
        silence_duration:  Seconds of consecutive silence to trigger stop.
        max_duration:      Hard cap on recording length.
        pre_roll_ms:       Keep this many ms of audio before speech onset.

    Returns:
        Float32 numpy array of shape (N,).

    Raises:
        RuntimeError: If sounddevice is not installed.
    """
    try:
        import sounddevice as sd
        import numpy as np
        import queue as Q
    except ImportError as exc:
        raise RuntimeError("sounddevice not installed: pip install sounddevice") from exc

    q: Q.Queue = Q.Queue()
    silence_frames_needed = int(silence_duration * SAMPLE_RATE / _CHUNK_FRAMES)
    max_chunks = int(max_duration * SAMPLE_RATE / _CHUNK_FRAMES)
    pre_roll_chunks = max(1, int(pre_roll_ms / 1000 * SAMPLE_RATE / _CHUNK_FRAMES))

    def _cb(indata, frames, time_info, status):
        q.put_nowait(indata.copy())

    chunks: list = []
    silent_count = 0
    has_speech = False

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                        blocksize=_CHUNK_FRAMES, callback=_cb):
        logger.debug("Recording (silence_threshold=%.3f)...", silence_threshold)
        for _ in range(max_chunks):
            chunk = await asyncio.to_thread(q.get)
            chunks.append(chunk)
            rms = float(np.sqrt(np.mean(chunk ** 2)))

            if rms > silence_threshold:
                has_speech = True
                silent_count = 0
            elif has_speech:
                silent_count += 1
                if silent_count >= silence_frames_needed:
                    logger.debug("Silence detected — stopping capture")
                    break

    if not chunks:
        return np.zeros(0, dtype=np.float32)

    return np.concatenate(chunks).flatten()


async def stream_microphone(
    chunk_size: int = _CHUNK_FRAMES,
) -> AsyncGenerator[bytes, None]:
    """Continuously yield raw PCM bytes from the default microphone.

    Each chunk is ``chunk_size`` frames of signed 16-bit mono at SAMPLE_RATE.
    Callers should convert to float32 via:
        ``np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0``

    Args:
        chunk_size: Number of audio frames per chunk.

    Yields:
        Raw int16 PCM byte strings.

    Raises:
        RuntimeError: If sounddevice is not installed.
    """
    try:
        import sounddevice as sd
        import queue as Q
    except ImportError as exc:
        raise RuntimeError("sounddevice not installed: pip install sounddevice") from exc

    q: Q.Queue = Q.Queue()

    def _cb(indata, frames, time_info, status):
        q.put_nowait(bytes(indata))

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                        blocksize=chunk_size, callback=_cb):
        logger.debug("Microphone stream started (chunk=%d frames)", chunk_size)
        while True:
            chunk = await asyncio.to_thread(q.get)
            yield chunk
