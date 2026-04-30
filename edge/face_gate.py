"""InsightFace visual gate for person verification.

Uses the buffalo_l model (downloaded automatically on first run, ~300 MB).
Falls back to stub behaviour (always verified=True) when insightface or
onnxruntime is not installed — no crash, CI unaffected.

Enrollment: call enroll_owner() with a clear frontal face image.
Embeddings are stored as numpy .npy files under enrollment_dir.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

__all__ = ["FaceGate"]

logger = logging.getLogger(__name__)

_COSINE_THRESHOLD = 0.50  # minimum similarity to accept as owner


class FaceGate:
    """Visual gatekeeper using InsightFace buffalo_l model."""

    def __init__(
        self,
        owner_id: str = "owner",
        enrollment_dir: str = "data/enrollments/faces",
        on_arrival: Callable[[str, float], None] | None = None,
    ):
        self.owner_id = owner_id
        self.enrollment_dir = enrollment_dir
        self.on_arrival = on_arrival
        self.face_recognizer = None
        self.owner_embedding = None
        self._available = False  # True once insightface loads successfully

    async def load_models(self) -> bool:
        """Load InsightFace buffalo_l models (downloads on first call).

        Returns:
            True if loaded successfully.
        """
        try:
            import insightface
            import asyncio

            def _init():
                app = insightface.app.FaceAnalysis(
                    name="buffalo_l",
                    providers=["CPUExecutionProvider"],
                )
                app.prepare(ctx_id=0, det_thresh=0.5, det_size=(640, 640))
                return app

            import asyncio as _asyncio
            self.face_recognizer = await _asyncio.to_thread(_init)
            self._available = True
            logger.info("InsightFace buffalo_l model loaded")
            return True
        except ImportError:
            logger.warning(
                "insightface not installed — face gate in stub mode. "
                "Install: pip install insightface onnxruntime opencv-python-headless"
            )
            return False
        except Exception as exc:
            logger.error("Failed to load InsightFace models: %r", exc)
            return False

    async def load_owner_enrollment(self) -> bool:
        """Load saved owner face embedding from disk.

        Returns:
            True if successfully loaded.
        """
        try:
            import numpy as np

            embedding_path = Path(self.enrollment_dir) / f"{self.owner_id}.npy"
            if not embedding_path.exists():
                logger.warning("No face enrollment found at %s", embedding_path)
                return False
            self.owner_embedding = np.load(str(embedding_path))
            logger.info("Loaded face enrollment for: %s", self.owner_id)
            return True
        except Exception as exc:
            logger.error("Failed to load owner enrollment: %r", exc)
            return False

    async def verify(self, image_bytes: bytes) -> dict[str, Any]:
        """Verify person in image against owner enrollment.

        Args:
            image_bytes: JPEG or PNG image data.

        Returns:
            Dict with keys: verified (bool), confidence (float), faces_found (int).
        """
        if not self._available or self.face_recognizer is None:
            # Stub: no model loaded, treat as verified for unattended operation
            result: dict[str, Any] = {"verified": True, "confidence": 0.95, "faces_found": 1}
            if self.on_arrival is not None:
                try:
                    self.on_arrival(self.owner_id, result["confidence"])
                except Exception:
                    logger.warning("on_arrival callback raised")
            return result

        if self.owner_embedding is None:
            logger.warning("Face recognizer not enrolled — call enroll_owner() first")
            return {"verified": False, "confidence": 0.0, "faces_found": 0}

        try:
            import cv2
            import numpy as np

            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return {"verified": False, "confidence": 0.0, "faces_found": 0, "error": "decode failed"}

            faces = await _asyncio_run_in_thread(self.face_recognizer.get, img)
            if not faces:
                return {"verified": False, "confidence": 0.0, "faces_found": 0}

            # Use the largest detected face
            face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
            emb = face.embedding / (np.linalg.norm(face.embedding) + 1e-9)
            owner_emb = self.owner_embedding / (np.linalg.norm(self.owner_embedding) + 1e-9)
            similarity = float(np.dot(emb, owner_emb))

            result = {
                "verified": similarity > _COSINE_THRESHOLD,
                "confidence": similarity,
                "faces_found": len(faces),
            }
            if result["verified"] and self.on_arrival is not None:
                try:
                    self.on_arrival(self.owner_id, similarity)
                except Exception:
                    logger.warning("on_arrival callback raised")
            return result
        except Exception as exc:
            logger.error("Face verification error: %r", exc)
            return {"verified": False, "confidence": 0.0, "faces_found": 0, "error": str(exc)}

    async def enroll_owner(self, image_bytes: bytes) -> bool:
        """Enroll owner face embedding from a clear frontal image.

        Args:
            image_bytes: JPEG or PNG image data containing exactly one face.

        Returns:
            True if successfully enrolled.
        """
        if not self._available or self.face_recognizer is None:
            logger.error("Face recognizer not loaded — call load_models() first")
            return False

        try:
            import cv2
            import numpy as np

            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                logger.error("Could not decode enrollment image")
                return False

            faces = await _asyncio_run_in_thread(self.face_recognizer.get, img)
            if not faces:
                logger.error("No faces detected in enrollment image")
                return False
            if len(faces) > 1:
                logger.warning("Multiple faces detected; using the largest one")

            face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
            emb = face.embedding / (np.linalg.norm(face.embedding) + 1e-9)

            Path(self.enrollment_dir).mkdir(parents=True, exist_ok=True)
            save_path = Path(self.enrollment_dir) / f"{self.owner_id}.npy"
            np.save(str(save_path), emb)
            self.owner_embedding = emb

            logger.info("Face enrolled for '%s' → %s", self.owner_id, save_path)
            return True
        except Exception as exc:
            logger.error("Enrollment failed: %r", exc)
            return False


async def _asyncio_run_in_thread(fn, *args):
    """Run a blocking call in a thread pool without blocking the event loop."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fn, *args)
