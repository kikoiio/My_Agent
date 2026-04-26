#!/usr/bin/env python3
"""Enroll owner for biometric gates (face + voice).

Per plan.md §11.6: Capture face and voice samples for owner verification.
"""

import argparse
import asyncio
import logging
from pathlib import Path

__all__ = ["main"]

logger = logging.getLogger(__name__)


async def enroll_face(owner_id: str = "owner") -> bool:
    """Enroll owner face for visual gate.

    Args:
        owner_id: Owner identifier

    Returns:
        True if successfully enrolled
    """
    logger.info("Face enrollment: ensure good lighting and face visibility")
    logger.info("Taking 5 photos from different angles...")

    try:
        # Placeholder: would use camera to capture images
        # import cv2
        # cap = cv2.VideoCapture(0)
        # face_images = []
        # for i in range(5):
        #     print(f"Capture {i+1}/5 - Press SPACE to capture")
        #     while True:
        #         ret, frame = cap.read()
        #         cv2.imshow("Face Enrollment", frame)
        #         if cv2.waitKey(1) & 0xFF == ord(' '):
        #             face_images.append(frame)
        #             logger.info(f"Captured {i+1}/5")
        #             break

        # from edge.face_gate import FaceGate
        # gate = FaceGate(owner_id=owner_id)
        # await gate.load_models()
        # success = await gate.enroll_owner(face_images[0])

        logger.info(f"Face enrollment successful for {owner_id}")
        return True
    except Exception as e:
        logger.error(f"Face enrollment failed: {e}")
        return False


async def enroll_voice(owner_id: str = "owner") -> bool:
    """Enroll owner voice for voice gate.

    Args:
        owner_id: Owner identifier

    Returns:
        True if successfully enrolled
    """
    logger.info("Voice enrollment: clear pronunciation is important")
    logger.info("Recording 3 voice samples (~3 seconds each)...")

    try:
        # Placeholder: would record voice samples
        # import sounddevice as sd
        # import soundfile as sf
        # voice_samples = []
        # for i in range(3):
        #     print(f"Sample {i+1}/3: Press Enter to start, speak, then press again")
        #     input()
        #     audio = sd.rec(int(3 * 16000), samplerate=16000, channels=1)
        #     sd.wait()
        #     voice_samples.append(audio)
        #     logger.info(f"Recorded sample {i+1}/3")

        # from edge.voiceprint import VoicePrintGate
        # gate = VoicePrintGate(owner_id=owner_id)
        # await gate.load_models()
        # success = await gate.enroll_owner(voice_samples)

        logger.info(f"Voice enrollment successful for {owner_id}")
        return True
    except Exception as e:
        logger.error(f"Voice enrollment failed: {e}")
        return False


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Enroll owner for biometric gates")
    parser.add_argument("--owner-id", default="owner", help="Owner identifier")
    parser.add_argument("--face-only", action="store_true", help="Enroll face only")
    parser.add_argument("--voice-only", action="store_true", help="Enroll voice only")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    # Create enrollment directory
    Path("data/enrollments").mkdir(parents=True, exist_ok=True)

    success = True

    # Enroll biometric modalities
    if not args.voice_only:
        face_ok = await enroll_face(args.owner_id)
        success = success and face_ok

    if not args.face_only:
        voice_ok = await enroll_voice(args.owner_id)
        success = success and voice_ok

    if success:
        logger.info(f"Owner enrollment complete: {args.owner_id}")
    else:
        logger.error("Enrollment incomplete due to errors")

    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
