"""Wake word detection using faster-whisper keyword spotting.

Strategy: slide a 2-second window over the continuous mic stream, run
faster-whisper "tiny" on each window, check whether the persona name appears
in the transcript.  50% window overlap keeps latency under 1 second.

Why not openwakeword: no pre-trained Chinese models available; training from
scratch requires hundreds of samples.  Whisper-based detection works
immediately with zero training data.

When faster-whisper is not installed the listener silently never fires
(same behaviour as the original stub), so CI / text-only mode is unaffected.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, AsyncGenerator

__all__ = ["WakeWordListener", "MultiWakeWordListener", "load_wake_words_from_personas"]

logger = logging.getLogger(__name__)

# 2-second window at 16 kHz
_WINDOW_FRAMES = 32_000
_CHUNK_DTYPE = "int16"

# Module-level tiny-model singleton for wake word (faster than 'base')
_tiny_model = None
_tiny_lock = None


def _get_tiny_model():
    """Return cached tiny WhisperModel for low-latency keyword spotting."""
    global _tiny_model, _tiny_lock
    import threading
    if _tiny_lock is None:
        _tiny_lock = threading.Lock()
    with _tiny_lock:
        if _tiny_model is None:
            try:
                from faster_whisper import WhisperModel
                _tiny_model = WhisperModel("tiny", device="cpu", compute_type="int8")
                logger.info("Loaded tiny Whisper model for wake word detection")
            except ImportError:
                logger.warning(
                    "faster-whisper not installed — wake word detection disabled. "
                    "Install: pip install faster-whisper"
                )
    return _tiny_model


def _keyword_in_text(keyword: str, text: str) -> bool:
    """Return True if keyword (or a close phonetic variant) appears in text."""
    kw = keyword.lower().strip()
    txt = text.lower()
    if kw in txt:
        return True
    # Common phonetic near-misses for Chinese names transliterated
    _PHONETIC: dict[str, list[str]] = {
        "小安": ["xiao an", "xiaoann", "小安", "晓安"],
        "晓林": ["xiao lin", "xiaolin", "晓林", "小林"],
        "小林": ["xiao lin", "xiaolin", "晓林", "小林"],
        "kobe": ["kobe", "科比", "koby"],
        "assistant": ["assistant", "小安", "助手"],
    }
    for alias in _PHONETIC.get(keyword, []):
        if alias.lower() in txt:
            return True
    return False


class WakeWordListener:
    """Single wake word detector using Whisper keyword spotting."""

    def __init__(
        self,
        persona: str,
        model_path: str | None = None,
        threshold: float = 0.5,
    ):
        self.persona = persona
        self.model_path = model_path  # kept for API compat; unused with Whisper approach
        self.threshold = threshold
        self.model = None
        self.running = False

    async def load_model(self) -> bool:
        """Pre-load the Whisper tiny model (optional; lazy-loaded on first listen)."""
        model = _get_tiny_model()
        self.model = model
        return model is not None

    async def listen(self, audio_stream: Any) -> AsyncGenerator[tuple[str, float], None]:
        """Listen for wake word in audio stream.

        Args:
            audio_stream: Async generator yielding int16 PCM byte chunks at 16 kHz.

        Yields:
            (persona, confidence) when wake word detected.
        """
        import numpy as np

        model = _get_tiny_model()
        if model is None:
            # faster-whisper not installed — silent stub (never fires)
            self.running = True
            try:
                async for _ in audio_stream:
                    pass
            finally:
                self.running = False
            return

        self.running = True
        buf = np.array([], dtype=np.float32)
        cooldown_chunks = 0  # prevent double-triggering

        try:
            async for raw_chunk in audio_stream:
                if not self.running:
                    break

                # Convert int16 bytes → float32
                arr = np.frombuffer(raw_chunk, dtype=np.int16).astype(np.float32) / 32768.0
                buf = np.concatenate([buf, arr])

                if len(buf) < _WINDOW_FRAMES:
                    continue

                if cooldown_chunks > 0:
                    cooldown_chunks -= 1
                    buf = buf[_WINDOW_FRAMES // 2:]
                    continue

                window = buf[:_WINDOW_FRAMES]
                # 50% overlap: keep the second half for the next window
                buf = buf[_WINDOW_FRAMES // 2:]

                try:
                    segments, _info = await asyncio.to_thread(
                        lambda w=window: tuple(
                            model.transcribe(
                                w,
                                language="zh",
                                condition_on_previous_text=False,
                                vad_filter=True,
                            )
                        )
                    )
                    text = "".join(s.text for s in segments)
                    if text.strip():
                        logger.debug("Wake window transcript: %r", text)
                    if _keyword_in_text(self.persona, text):
                        logger.info("Wake word '%s' detected in: %r", self.persona, text)
                        cooldown_chunks = 6  # ~3 seconds cooldown
                        yield (self.persona, 0.85)
                except Exception as exc:
                    logger.debug("Wake word transcription error: %r", exc)
        finally:
            self.running = False

    async def stop(self) -> None:
        """Stop listening."""
        self.running = False


class MultiWakeWordListener:
    """Manage N concurrent wake word listeners on a shared audio stream."""

    def __init__(self, personas: list[str]):
        self.personas = personas
        self.listeners = {p: WakeWordListener(p) for p in personas}
        self.listen_tasks: list[asyncio.Task] = []

    async def start_listeners(self, audio_stream: Any) -> None:
        """Start all listeners on a shared audio stream."""
        for persona, listener in self.listeners.items():
            task = asyncio.create_task(self._listener_loop(listener, audio_stream))
            self.listen_tasks.append(task)
        logger.info("Started %d wake word listeners", len(self.listeners))

    async def _listener_loop(self, listener: WakeWordListener, audio_stream: Any) -> None:
        try:
            async for persona, confidence in listener.listen(audio_stream):
                logger.info("Wake word detected: %s (confidence=%.2f)", persona, confidence)
        except Exception as exc:
            logger.error("Listener error for %s: %r", listener.persona, exc)

    async def stop_all(self) -> None:
        """Stop all listeners."""
        for listener in self.listeners.values():
            await listener.stop()
        for task in self.listen_tasks:
            task.cancel()
        try:
            await asyncio.gather(*self.listen_tasks)
        except asyncio.CancelledError:
            pass
        logger.info("All wake word listeners stopped")

    async def get_active_listeners(self) -> list[str]:
        return [p for p, l in self.listeners.items() if l.running]


def load_wake_words_from_personas(personas_dir: str | Path = "personas") -> dict[str, str]:
    """Build a {wake_word: persona_id} mapping from all persona directories.

    Reads each persona's persona.yaml (if present) for the ``wake_word`` field.
    Falls back to the directory name when the field is absent.

    Returns:
        Dict mapping wake word string → persona directory name (persona_id).
    """
    import yaml

    root = Path(personas_dir)
    if not root.is_dir():
        return {}

    result: dict[str, str] = {}
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("_") or d.name.startswith("."):
            continue
        persona_id = d.name
        persona_yaml = d / "persona.yaml"
        wake_word = persona_id
        if persona_yaml.exists():
            try:
                meta = yaml.safe_load(persona_yaml.read_text(encoding="utf-8")) or {}
                wake_word = meta.get("wake_word") or meta.get("name") or persona_id
            except Exception as exc:
                logger.warning("Failed to read persona.yaml for %s: %r", persona_id, exc)
        result[wake_word] = persona_id

    logger.debug("Loaded %d wake words: %s", len(result), list(result.keys()))
    return result
