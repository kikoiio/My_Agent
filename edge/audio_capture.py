"""Microphone capture utilities using sounddevice.

Provides two capture modes:
  1. capture_fixed_duration()  — record exactly N seconds of audio
  2. capture_until_silence()   — record until the user stops speaking (energy VAD)
  3. stream_microphone()       — continuous async generator of raw PCM chunks

All audio is returned as 16 kHz mono float32 unless otherwise noted.

Windows note:
  MME host API often rejects mono / 16 kHz requests (e.g. C922 only supports
  stereo 44100 in MME mode).  _find_input_device() prefers WASAPI and
  auto-detects the native sample rate; _resample() handles the conversion.
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

SAMPLE_RATE = 16_000          # target Hz for all returned audio
_CHUNK_FRAMES = 1_600         # 100 ms at 16 kHz


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_input_device() -> tuple[int | None, int]:
    """Return (device_id, native_sample_rate) for the best available input.

    Priority: WASAPI > DirectSound > MME.
    Falls back to the sounddevice default input device when no preferred API
    is found.
    """
    import sounddevice as sd

    apis = sd.query_hostapis()
    devices = sd.query_devices()

    preferred_apis = ["Windows WASAPI", "Windows DirectSound", "MME",
                      "Core Audio", "ALSA", "OSS"]  # rough cross-platform priority

    for preferred in preferred_apis:
        idx = next((i for i, a in enumerate(apis) if preferred in a["name"]), None)
        if idx is None:
            continue
        for dev_id, dev in enumerate(devices):
            if dev["hostapi"] == idx and dev["max_input_channels"] > 0:
                sr = int(dev["default_samplerate"]) or SAMPLE_RATE
                logger.debug(
                    "Selected input device [%d] %s | api=%s | sr=%d",
                    dev_id, dev["name"], preferred, sr,
                )
                return dev_id, sr

    # Fall back to sounddevice default
    try:
        info = sd.query_devices(kind="input")
        sr = int(info.get("default_samplerate") or SAMPLE_RATE)
        return None, sr
    except Exception:
        return None, SAMPLE_RATE


def _resample(audio: "numpy.ndarray", from_sr: int, to_sr: int) -> "numpy.ndarray":
    """Resample a float32 mono array using linear interpolation.

    Good enough for speech; avoids heavy scipy/librosa dependency.
    """
    import numpy as np

    if from_sr == to_sr:
        return audio
    n_target = int(len(audio) * to_sr / from_sr)
    return np.interp(
        np.linspace(0, len(audio) - 1, n_target),
        np.arange(len(audio)),
        audio,
    ).astype(np.float32)


def _record_blocking(seconds: float) -> "numpy.ndarray":
    """Blocking audio capture — runs in a thread, returns 16 kHz mono float32.

    Tries stereo then mono to handle devices that don't expose mono in MME.
    Always resamples to SAMPLE_RATE.
    """
    import sounddevice as sd
    import numpy as np

    device_id, native_sr = _find_input_device()
    frames = int(seconds * native_sr)

    last_err: Exception | None = None
    for channels in [2, 1]:
        try:
            raw = sd.rec(
                frames,
                samplerate=native_sr,
                channels=channels,
                dtype="float32",
                device=device_id,
            )
            sd.wait()
            # Stereo → mono
            mono = raw.mean(axis=1) if channels == 2 else raw.flatten()
            return _resample(mono, native_sr, SAMPLE_RATE)
        except Exception as exc:
            last_err = exc
            logger.debug("Recording failed with channels=%d: %r", channels, exc)

    raise RuntimeError(f"Audio recording failed: {last_err}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def capture_fixed_duration(seconds: float = 5.0) -> "numpy.ndarray":
    """Record a fixed duration of audio from the default microphone.

    Args:
        seconds: Duration in seconds.

    Returns:
        Float32 numpy array of shape (N,) at SAMPLE_RATE (16 kHz mono).

    Raises:
        RuntimeError: If sounddevice is not installed or recording fails.
    """
    try:
        import sounddevice  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("sounddevice not installed: pip install sounddevice") from exc

    logger.debug("Capturing %.1f s of audio", seconds)
    return await asyncio.to_thread(_record_blocking, seconds)


async def capture_until_silence(
    silence_threshold: float = 0.015,
    silence_duration: float = 1.5,
    max_duration: float = 10.0,
) -> "numpy.ndarray":
    """Record until the speaker stops talking (energy-based VAD).

    Stops when RMS energy stays below ``silence_threshold`` for
    ``silence_duration`` consecutive seconds, or after ``max_duration`` total.

    Args:
        silence_threshold: RMS energy threshold (0–1) for silence.
        silence_duration:  Seconds of silence needed to stop.
        max_duration:      Hard cap on recording length (seconds).

    Returns:
        Float32 numpy array of shape (N,) at SAMPLE_RATE.

    Raises:
        RuntimeError: If sounddevice is not installed.
    """
    try:
        import sounddevice as sd
        import numpy as np
        import queue as Q
    except ImportError as exc:
        raise RuntimeError("sounddevice not installed: pip install sounddevice") from exc

    device_id, native_sr = _find_input_device()

    # Chunk size in native frames (≈100 ms)
    chunk_frames_native = max(1, int(0.1 * native_sr))
    silence_chunks_needed = max(1, int(silence_duration / 0.1))
    max_chunks = max(1, int(max_duration / 0.1))

    q: Q.Queue = Q.Queue()

    def _cb(indata, frames, time_info, status):
        q.put_nowait(indata.copy())

    chunks: list = []
    silent_count = 0
    has_speech = False

    # Try stereo first (safer on Windows MME)
    last_err: Exception | None = None
    for channels in [2, 1]:
        try:
            ctx = sd.InputStream(
                samplerate=native_sr,
                channels=channels,
                dtype="float32",
                blocksize=chunk_frames_native,
                callback=_cb,
                device=device_id,
            )
            ctx.__enter__()
            break
        except Exception as exc:
            last_err = exc
            logger.debug("InputStream failed with channels=%d: %r", channels, exc)
            ctx = None  # type: ignore[assignment]
    else:
        raise RuntimeError(f"Cannot open microphone: {last_err}")

    # Clear any queued garbage from failed attempts
    while not q.empty():
        try:
            q.get_nowait()
        except Exception:
            break

    try:
        logger.debug("VAD recording (threshold=%.3f, native_sr=%d)...",
                     silence_threshold, native_sr)
        for _ in range(max_chunks):
            chunk = await asyncio.to_thread(q.get)
            # Stereo → mono if needed
            mono_chunk = chunk.mean(axis=1) if chunk.ndim > 1 and chunk.shape[1] > 1 else chunk.flatten()
            chunks.append(mono_chunk)

            rms = float(np.sqrt(np.mean(mono_chunk ** 2)))
            if rms > silence_threshold:
                has_speech = True
                silent_count = 0
            elif has_speech:
                silent_count += 1
                if silent_count >= silence_chunks_needed:
                    logger.debug("Silence detected, stopping capture")
                    break
    finally:
        ctx.__exit__(None, None, None)

    if not chunks:
        import numpy as np
        return np.zeros(0, dtype=np.float32)

    import numpy as np
    combined = np.concatenate(chunks)
    return _resample(combined, native_sr, SAMPLE_RATE)


async def stream_microphone(
    chunk_size: int = _CHUNK_FRAMES,
) -> AsyncGenerator[bytes, None]:
    """Continuously yield raw PCM bytes from the default microphone.

    Each yielded chunk is ``chunk_size`` frames of signed 16-bit mono at
    SAMPLE_RATE (16 kHz).  Internally the device may capture at a higher
    sample rate and in stereo; this function handles the conversion.

    Callers convert to float32 via:
        ``np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0``

    Args:
        chunk_size: Number of *output* frames per chunk (at SAMPLE_RATE).

    Yields:
        Raw int16 PCM byte strings at SAMPLE_RATE mono.

    Raises:
        RuntimeError: If sounddevice is not installed.
    """
    try:
        import sounddevice as sd
        import numpy as np
        import queue as Q
    except ImportError as exc:
        raise RuntimeError("sounddevice not installed: pip install sounddevice") from exc

    device_id, native_sr = _find_input_device()
    # Native chunk ≈ same wall-clock duration as requested output chunk
    native_chunk = max(1, int(chunk_size * native_sr / SAMPLE_RATE))

    q: Q.Queue = Q.Queue()

    def _cb(indata, frames, time_info, status):
        q.put_nowait(indata.copy())

    last_err: Exception | None = None
    for channels in [2, 1]:
        try:
            ctx = sd.InputStream(
                samplerate=native_sr,
                channels=channels,
                dtype="int16",
                blocksize=native_chunk,
                callback=_cb,
                device=device_id,
            )
            ctx.__enter__()
            _channels_used = channels
            break
        except Exception as exc:
            last_err = exc
            ctx = None  # type: ignore[assignment]
    else:
        raise RuntimeError(f"Cannot open microphone: {last_err}")

    logger.debug(
        "Microphone stream started: device=%s ch=%d native_sr=%d",
        device_id, _channels_used, native_sr,
    )

    try:
        leftover = np.array([], dtype=np.float32)

        while True:
            raw = await asyncio.to_thread(q.get)
            # Stereo → mono
            mono = raw.mean(axis=1).astype(np.float32) / 32768.0 if raw.ndim > 1 and raw.shape[1] > 1 \
                   else raw.flatten().astype(np.float32) / 32768.0
            # Resample to SAMPLE_RATE
            resampled = _resample(mono, native_sr, SAMPLE_RATE)
            combined = np.concatenate([leftover, resampled])

            # Yield full chunks at output size
            n = len(combined) // chunk_size
            for i in range(n):
                slice_ = combined[i * chunk_size:(i + 1) * chunk_size]
                yield (slice_ * 32767).astype(np.int16).tobytes()

            leftover = combined[n * chunk_size:]
    finally:
        ctx.__exit__(None, None, None)
