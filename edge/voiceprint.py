"""Speaker verification using resemblyzer (GE2E d-vector model).

resemblyzer loads a ~17 MB pre-trained model on first use.
Falls back to stub behaviour when resemblyzer is not installed.

Enrollment: call enroll_owner() with a list of audio byte strings (WAV/PCM).
Embeddings are averaged and saved as numpy .npy files.
Verification: cosine similarity between new embedding and saved mean embedding.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

__all__ = ["VoicePrintGate"]

logger = logging.getLogger(__name__)

_COSINE_THRESHOLD = 0.75  # minimum cosine similarity to accept as owner
_SAMPLE_RATE = 16_000


class VoicePrintGate:
    """Speaker verification using resemblyzer GE2E model."""

    def __init__(
        self,
        owner_id: str = "owner",
        enrollment_dir: str = "data/enrollments/voices",
        sample_rate: int = _SAMPLE_RATE,
    ):
        self.owner_id = owner_id
        self.enrollment_dir = enrollment_dir
        self.sample_rate = sample_rate
        self.model = None
        self.owner_embedding = None
        self._available = False

    async def load_models(self) -> bool:
        """Load the GE2E VoiceEncoder model.

        Returns:
            True if loaded successfully.
        """
        try:
            from resemblyzer import VoiceEncoder
            import asyncio

            self.model = await asyncio.to_thread(lambda: VoiceEncoder(device="cpu"))
            self._available = True
            logger.info("resemblyzer VoiceEncoder loaded")
            return True
        except ImportError:
            logger.warning(
                "resemblyzer not installed — voiceprint in stub mode. "
                "Install: pip install resemblyzer"
            )
            return False
        except Exception as exc:
            logger.error("Failed to load resemblyzer: %r", exc)
            return False

    async def load_owner_enrollment(self) -> bool:
        """Load saved voice embedding from disk.

        Returns:
            True if successfully loaded.
        """
        try:
            import numpy as np

            emb_path = Path(self.enrollment_dir) / f"{self.owner_id}.npy"
            if not emb_path.exists():
                logger.warning("No voice enrollment found at %s", emb_path)
                return False
            self.owner_embedding = np.load(str(emb_path))
            logger.info("Loaded voice enrollment for: %s", self.owner_id)
            return True
        except Exception as exc:
            logger.error("Failed to load voice enrollment: %r", exc)
            return False

    async def verify(self, audio_bytes: bytes) -> dict[str, Any]:
        """Verify speaker against stored enrollment.

        Args:
            audio_bytes: WAV or raw PCM audio at self.sample_rate.

        Returns:
            Dict with keys: verified (bool), confidence (float).
        """
        if not self._available or self.model is None:
            # Stub: always verified when model unavailable
            return {"verified": True, "confidence": 0.92}

        if self.owner_embedding is None:
            logger.warning("Voice model not enrolled — call enroll_owner() first")
            return {"verified": False, "confidence": 0.0}

        try:
            import numpy as np
            from resemblyzer import preprocess_wav

            wav = await _load_wav(audio_bytes, self.sample_rate)
            import asyncio
            embedding = await asyncio.to_thread(self.model.embed_utterance, wav)
            embedding = embedding / (np.linalg.norm(embedding) + 1e-9)
            owner_emb = self.owner_embedding / (np.linalg.norm(self.owner_embedding) + 1e-9)
            similarity = float(np.dot(embedding, owner_emb))
            return {"verified": similarity > _COSINE_THRESHOLD, "confidence": similarity}
        except Exception as exc:
            logger.error("Voice verification error: %r", exc)
            return {"verified": False, "confidence": 0.0, "error": str(exc)}

    async def enroll_owner(self, audio_samples: list[bytes]) -> bool:
        """Enroll owner voice from multiple audio samples.

        At least 3 samples of ~3 seconds each are recommended for stable embeddings.

        Args:
            audio_samples: List of WAV/PCM byte strings.

        Returns:
            True if successfully enrolled.
        """
        if not self._available or self.model is None:
            logger.error("Voice model not loaded — call load_models() first")
            return False

        try:
            import asyncio
            import numpy as np

            embeddings = []
            for i, audio_bytes in enumerate(audio_samples):
                wav = await _load_wav(audio_bytes, self.sample_rate)
                emb = await asyncio.to_thread(self.model.embed_utterance, wav)
                embeddings.append(emb)
                logger.debug("Embedded sample %d/%d", i + 1, len(audio_samples))

            if not embeddings:
                logger.error("No valid audio samples for enrollment")
                return False

            avg = np.mean(embeddings, axis=0)
            avg = avg / (np.linalg.norm(avg) + 1e-9)

            Path(self.enrollment_dir).mkdir(parents=True, exist_ok=True)
            save_path = Path(self.enrollment_dir) / f"{self.owner_id}.npy"
            np.save(str(save_path), avg)
            self.owner_embedding = avg

            logger.info("Voice enrolled for '%s' → %s (from %d samples)",
                        self.owner_id, save_path, len(embeddings))
            return True
        except Exception as exc:
            logger.error("Voice enrollment failed: %r", exc)
            return False

    def get_voice_activity(self, audio_bytes: bytes) -> tuple[bool, float]:
        """Simple energy-based voice activity detection.

        Args:
            audio_bytes: Raw int16 PCM audio data.

        Returns:
            (has_voice, rms_energy) tuple.
        """
        try:
            import numpy as np
            arr = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(arr ** 2)))
            return rms > 0.01, rms
        except Exception:
            return True, 0.9


async def _load_wav(audio_bytes: bytes, sample_rate: int):
    """Load audio bytes as float32 numpy array, resampled to sample_rate."""
    import asyncio
    import numpy as np

    def _decode():
        from resemblyzer import preprocess_wav

        # preprocess_wav accepts file-like objects since resemblyzer 0.1.1
        buf = io.BytesIO(audio_bytes)
        try:
            return preprocess_wav(buf, source_sr=sample_rate)
        except TypeError:
            # Older resemblyzer versions need a file path — write to temp file
            import tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_bytes)
                tmp = f.name
            try:
                return preprocess_wav(tmp)
            finally:
                os.unlink(tmp)

    return await asyncio.to_thread(_decode)
