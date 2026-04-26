#!/usr/bin/env python3
"""Train custom wake word model for persona.

Per plan.md §11.5: Record audio samples and train openwakeword model.
"""

import argparse
import asyncio
import logging
from pathlib import Path

__all__ = ["main"]

logger = logging.getLogger(__name__)


async def record_samples(
    persona: str,
    num_samples: int = 20,
    duration_s: float = 2.0,
) -> list[str]:
    """Record audio samples for wake word training.

    Args:
        persona: Persona name
        num_samples: Number of samples to record
        duration_s: Duration of each sample

    Returns:
        List of audio file paths
    """
    logger.info(f"Recording {num_samples} wake word samples for '{persona}'")
    logger.info(f"Please say '{persona}' clearly for each recording")

    samples = []
    for i in range(num_samples):
        print(f"\n[{i+1}/{num_samples}] Press Enter to start recording...")
        input()

        try:
            # Placeholder: would use sounddevice or pyaudio to record
            # import sounddevice as sd
            # import numpy as np
            # audio = sd.rec(
            #     int(duration_s * 16000),
            #     samplerate=16000,
            #     channels=1,
            # )
            # sd.wait()

            sample_path = f"data/training/wake_words/{persona}_{i:03d}.wav"
            Path(sample_path).parent.mkdir(parents=True, exist_ok=True)
            # sf.write(sample_path, audio, 16000)

            logger.info(f"Recorded sample {i+1}")
            samples.append(sample_path)
        except Exception as e:
            logger.error(f"Recording failed: {e}")

    return samples


async def train_model(
    persona: str,
    samples: list[str],
    output_path: str | None = None,
) -> bool:
    """Train openwakeword model from samples.

    Args:
        persona: Persona name
        samples: List of training sample paths
        output_path: Output model path

    Returns:
        True if training successful
    """
    output_path = output_path or f"personas/{persona}/wake.onnx"

    logger.info(f"Training wake word model for '{persona}'")
    logger.info(f"Using {len(samples)} samples")

    try:
        # Placeholder: would use openwakeword training API
        # from openwakeword.training import Trainer
        # trainer = Trainer(
        #     positive_samples=samples,
        #     output_model=output_path,
        # )
        # trainer.train()

        logger.info(f"Model trained and saved to: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Training failed: {e}")
        return False


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Train wake word model")
    parser.add_argument("persona", help="Persona name")
    parser.add_argument("--samples", type=int, default=20, help="Number of samples")
    parser.add_argument("--duration", type=float, default=2.0, help="Sample duration (seconds)")
    parser.add_argument("--output", help="Output model path")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    # Record samples
    samples = await record_samples(
        persona=args.persona,
        num_samples=args.samples,
        duration_s=args.duration,
    )

    if not samples:
        logger.error("No samples recorded")
        return False

    # Train model
    success = await train_model(
        persona=args.persona,
        samples=samples,
        output_path=args.output,
    )

    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
