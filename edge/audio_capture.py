"""Microphone capture utilities using sounddevice.

Provides two capture modes:
  1. capture_fixed_duration()  — record exactly N seconds of audio
  2. capture_until_silence()   — record until the user stops speaking (energy VAD)
  3. stream_microphone()       — continuous async generator of raw PCM chunks

All audio is returned as 16 kHz mono float32 unless otherwise noted.

Windows note:
  MME host API rejects mono / 16 kHz requests (e.g. C922 only supports stereo
  44100 via MME).  We always pass device=None (OS default) to avoid invalid
  device ID errors caused by USB adapter index misalignment, and request the
  native sample rate + stereo first.  Stereo → mono conversion and resampling
  to 16 kHz are done in Python via numpy.
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

_HOSTAPI_PRIORITY = (
    "Windows WDM-KS",   # most reliable for USB webcams (kernel streaming)
    "Windows WASAPI",   # modern, low-latency
    "Windows DirectSound",
    "MME",              # last resort, often -9999 with USB cams
)


def _find_input_device() -> tuple[object, int]:
    """Return (device_spec, native_sample_rate) preferring stable hostapis.

    On Windows the same physical mic appears under MME / DirectSound / WASAPI /
    WDM-KS hostapis.  Their reliability with USB webcams varies wildly:
      - MME often -9999 (Unanticipated host error)
      - DirectSound often -9999
      - WASAPI often -9996 (Invalid device) or -9997 (Invalid sample rate)
      - WDM-KS is the kernel-streaming layer and tends to just work
    So we walk hostapis in our priority order and return the first one whose
    name matches the OS default input device.  device_spec is an int index
    (passed to sd.InputStream as `device=int`).
    """
    import sounddevice as sd

    try:
        default_info = sd.query_devices(kind="input")
        default_name = default_info.get("name", "")
        default_sr = int(default_info.get("default_samplerate") or SAMPLE_RATE)

        try:
            hostapis = list(sd.query_hostapis())
            devices = list(sd.query_devices())
        except Exception as exc:
            logger.debug("query failed: %r", exc)
            return None, default_sr

        for preferred in _HOSTAPI_PRIORITY:
            ha_idx = next(
                (i for i, ha in enumerate(hostapis) if ha["name"] == preferred),
                None,
            )
            if ha_idx is None:
                continue
            for idx, dev in enumerate(devices):
                if dev["hostapi"] != ha_idx:
                    continue
                if dev["max_input_channels"] <= 0:
                    continue
                if dev["name"] == default_name or _name_overlap(dev["name"], default_name):
                    sr = int(dev.get("default_samplerate") or SAMPLE_RATE)
                    logger.debug(
                        "Selected %s input [%d] '%s' | sr=%d",
                        preferred, idx, dev["name"], sr,
                    )
                    return idx, sr

        logger.debug("Falling back to default input '%s' | sr=%d", default_name, default_sr)
        return None, default_sr
    except Exception:
        return None, SAMPLE_RATE


def _name_overlap(a: str, b: str) -> bool:
    """True if two device-name strings share a meaningful substring.

    sounddevice may rename a device slightly across hostapis (e.g.
    "麦克风 (C922 Pro Stream Webcam)" on MME vs "C922 Pro Stream Webcam"
    on WASAPI).  We match on the parenthesised model name.
    """
    import re
    pat = re.compile(r"\(([^)]+)\)")
    a_match = pat.search(a)
    b_match = pat.search(b)
    a_inner = a_match.group(1).strip().lower() if a_match else a.lower()
    b_inner = b_match.group(1).strip().lower() if b_match else b.lower()
    if not a_inner or not b_inner:
        return False
    return a_inner in b_inner or b_inner in a_inner


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

    Tries multiple (device, channels, sample_rate) combinations to handle
    Windows MME / WASAPI quirks.  Always resamples to SAMPLE_RATE.
    """
    import sounddevice as sd
    import numpy as np

    device_id, native_sr = _find_input_device()
    candidates = _candidate_input_specs(device_id, native_sr)

    last_err: Exception | None = None
    for spec in candidates:
        dev, sr, channels = spec["device"], spec["sr"], spec["channels"]
        try:
            frames = int(seconds * sr)
            raw = sd.rec(
                frames,
                samplerate=sr,
                channels=channels,
                dtype="float32",
                device=dev,
            )
            sd.wait()
            mono = raw.mean(axis=1) if channels == 2 else raw.flatten()
            logger.debug("Capture OK via device=%r sr=%d channels=%d", dev, sr, channels)
            return _resample(mono, sr, SAMPLE_RATE)
        except Exception as exc:
            last_err = exc
            logger.debug(
                "Recording failed (device=%r sr=%d channels=%d): %r",
                dev, sr, channels, exc,
            )

    raise RuntimeError(f"Audio recording failed: {last_err}")


def _candidate_input_specs(preferred_device, preferred_sr: int) -> list[dict]:
    """Build a list of (device, sample_rate, channels) combos to try.

    Order: preferred device + preferred sr first, then fallbacks.  Each combo
    is tried until one works.  This handles cases where a USB webcam advertises
    one sample rate but only accepts another, or where the device index is
    wrong but the device name resolves correctly.
    """
    import sounddevice as sd

    candidates: list[dict] = []
    # Always try the preferred (device, sr) first with both channel counts
    for ch in (1, 2):  # mono first — works on more drivers
        candidates.append({"device": preferred_device, "sr": preferred_sr, "channels": ch})
    # Other common sample rates
    for sr in (16000, 48000, 44100, 32000):
        if sr == preferred_sr:
            continue
        for ch in (1, 2):
            candidates.append({"device": preferred_device, "sr": sr, "channels": ch})
    # Fallback: device=None (whatever the OS default is) at every sample rate
    if preferred_device is not None:
        for sr in (preferred_sr, 16000, 48000, 44100, 32000):
            for ch in (1, 2):
                candidates.append({"device": None, "sr": sr, "channels": ch})
    # Final fallback: try device by name string of any USB-like input
    try:
        names_seen: set[str] = set()
        for dev in sd.query_devices():
            if dev["max_input_channels"] <= 0:
                continue
            name = dev["name"]
            # Pull "C922 Pro Stream Webcam" out of "麦克风 (C922 Pro Stream Webcam)"
            inner = name
            if "(" in name and ")" in name:
                inner = name[name.find("(") + 1 : name.rfind(")")]
            inner = inner.strip()
            if not inner or inner in names_seen:
                continue
            names_seen.add(inner)
            for sr in (16000, 48000, 44100):
                for ch in (1, 2):
                    candidates.append({"device": inner, "sr": sr, "channels": ch})
    except Exception:
        pass
    return candidates


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
