#!/usr/bin/env python3
"""Enroll owner biometrics (face + voice) for the gate system.

Face enrollment: Opens the default camera, lets you capture 5 photos from
different angles by pressing SPACE, then saves the average embedding.

Voice enrollment: Records 3 audio samples of ~4 seconds each, then saves the
averaged GE2E embedding for speaker verification.

Usage:
    python scripts/enroll_owner.py                  # both face + voice
    python scripts/enroll_owner.py --face-only
    python scripts/enroll_owner.py --voice-only
    python scripts/enroll_owner.py --owner-id alice
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

__all__ = ["main"]

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# --------------------------------------------------------------------------- #
# Face enrollment
# --------------------------------------------------------------------------- #

async def enroll_face(owner_id: str = "owner") -> bool:
    """Capture 5 face photos and save the enrollment embedding.

    Opens the default camera (index 0).  Press SPACE to capture each frame.
    """
    try:
        import cv2
    except ImportError:
        logger.error("opencv-python-headless not installed. Run: pip install opencv-python-headless")
        return False

    from edge.face_gate import FaceGate

    gate = FaceGate(owner_id=owner_id)
    if not await gate.load_models():
        logger.error("Could not load InsightFace models")
        return False

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        logger.error("Could not open camera (index 0)")
        return False

    print("\n[人脸注册] 请保持光线充足，正对摄像头。")
    print("按 SPACE 键拍摄，共需 5 张（不同角度）。按 Q 放弃。\n")

    captured_images: list[bytes] = []
    embeddings = []

    try:
        import numpy as np

        while len(captured_images) < 5:
            ret, frame = cap.read()
            if not ret:
                logger.error("Camera read failed")
                break

            overlay = frame.copy()
            cv2.putText(
                overlay,
                f"[{len(captured_images)}/5] SPACE=capture  Q=quit",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2,
            )
            cv2.imshow("Face Enrollment", overlay)

            key = cv2.waitKey(30) & 0xFF
            if key == ord("q"):
                print("放弃注册。")
                return False
            if key == ord(" "):
                _, buf = cv2.imencode(".jpg", frame)
                image_bytes = buf.tobytes()
                result = await gate.enroll_owner(image_bytes)
                if result:
                    captured_images.append(image_bytes)
                    print(f"  ✓ 拍摄 {len(captured_images)}/5")
                else:
                    print("  ✗ 未检测到人脸，请重试")
    finally:
        cap.release()
        cv2.destroyAllWindows()

    if len(captured_images) < 3:
        logger.error("Not enough face samples (need at least 3, got %d)", len(captured_images))
        return False

    print(f"\n✓ 人脸注册成功（{len(captured_images)} 张）→ data/enrollments/faces/{owner_id}.npy\n")
    return True


# --------------------------------------------------------------------------- #
# Voice enrollment
# --------------------------------------------------------------------------- #

async def enroll_voice(owner_id: str = "owner", num_samples: int = 3) -> bool:
    """Record voice samples and save the enrollment embedding.

    Uses edge.audio_capture.capture_fixed_duration which automatically handles
    Windows WASAPI / native sample rate / stereo-to-mono conversion.
    """
    try:
        import sounddevice  # noqa: F401  just to give an early friendly error
    except ImportError:
        logger.error("sounddevice not installed. Run: pip install sounddevice")
        return False

    from edge.voiceprint import VoicePrintGate
    from edge.audio_capture import capture_fixed_duration

    gate = VoicePrintGate(owner_id=owner_id)
    if not await gate.load_models():
        logger.error("Could not load resemblyzer model")
        return False

    print("\n[声纹注册] 将录制 %d 段音频，每段约 4 秒。" % num_samples)
    print("请说一段自然的中文（如自我介绍），录完后自动停止。\n")

    DURATION = 4.0
    SAMPLE_RATE = 16_000  # capture_fixed_duration always returns 16 kHz mono
    audio_samples: list[bytes] = []

    for i in range(num_samples):
        input(f"[{i+1}/{num_samples}] 按 Enter 开始录音...")
        print("  🎙  录音中... 请说话")

        try:
            # Returns float32 numpy array at 16 kHz mono (handles WASAPI/resample)
            audio_float = await capture_fixed_duration(DURATION)
        except Exception as exc:
            logger.error("录音失败: %r", exc)
            return False

        # Convert float32 → int16 WAV bytes for resemblyzer
        import io, wave, numpy as np
        audio_int16 = (np.clip(audio_float, -1.0, 1.0) * 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_int16.tobytes())
        audio_samples.append(buf.getvalue())
        print(f"  ✓ 录制完成 {i+1}/{num_samples}\n")

    success = await gate.enroll_owner(audio_samples)
    if success:
        print(f"✓ 声纹注册成功（{num_samples} 段）→ data/enrollments/voices/{owner_id}.npy\n")
    else:
        print("✗ 声纹注册失败")
    return success


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

async def main() -> bool:
    parser = argparse.ArgumentParser(description="注册主人生物特征（人脸 + 声纹）")
    parser.add_argument("--owner-id", default="owner", help="主人标识符（默认 owner）")
    parser.add_argument("--face-only", action="store_true", help="仅注册人脸")
    parser.add_argument("--voice-only", action="store_true", help="仅注册声纹")
    parser.add_argument("--voice-samples", type=int, default=3, help="声纹录音段数（默认 3）")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    Path("data/enrollments").mkdir(parents=True, exist_ok=True)

    success = True

    if not args.voice_only:
        face_ok = await enroll_face(args.owner_id)
        success = success and face_ok

    if not args.face_only:
        voice_ok = await enroll_voice(args.owner_id, num_samples=args.voice_samples)
        success = success and voice_ok

    if success:
        print("=" * 50)
        print(f"✓ 主人注册完成：{args.owner_id}")
        print(f"  人脸: data/enrollments/faces/{args.owner_id}.npy")
        print(f"  声纹: data/enrollments/voices/{args.owner_id}.npy")
        print("=" * 50)
    else:
        print("✗ 注册未完全成功，请检查上方错误信息")

    return success


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
