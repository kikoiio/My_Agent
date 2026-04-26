#!/usr/bin/env python3
"""Test persona TTS voice synthesis.

Per plan.md §11.8: Generate test audio to verify TTS quality.
"""

import argparse
import asyncio
import logging
from pathlib import Path

__all__ = ["main"]

logger = logging.getLogger(__name__)


async def synthesize_and_save(
    persona_name: str,
    text: str,
    output_path: str,
    tts_client: str = "cosyvoice",
) -> bool:
    """Synthesize text and save to file.

    Args:
        persona_name: Persona name
        text: Text to synthesize
        output_path: Output audio file path
        tts_client: TTS provider ("cosyvoice", "fishspeech", "piper")

    Returns:
        True if successful
    """
    try:
        logger.info(f"Synthesizing with {tts_client}: {text[:50]}...")

        # Load persona to get voice reference
        from core.persona import load

        persona_dir = Path("personas") / persona_name
        persona = load(persona_dir)

        logger.info(f"Using voice reference: {persona.voice_ref_text}")

        # Select TTS client
        if tts_client == "cosyvoice":
            from backend.tts.cosyvoice_client import CosyVoiceClient

            client = CosyVoiceClient()
        elif tts_client == "fishspeech":
            from backend.tts.fishspeech_client import FishSpeechClient

            client = FishSpeechClient()
        elif tts_client == "piper":
            from backend.tts.piper_client import PiperClient

            client = PiperClient()
        else:
            logger.error(f"Unknown TTS client: {tts_client}")
            return False

        # Synthesize
        audio_bytes = await client.synthesize(text)

        # Save to file
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio_bytes)

        logger.info(f"Saved audio to: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        return False


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Test persona voice synthesis")
    parser.add_argument("persona", help="Persona name")
    parser.add_argument("--text", default="Hello, I am a helpful AI assistant.", help="Text to synthesize")
    parser.add_argument("--output", help="Output audio file path")
    parser.add_argument("--tts", default="cosyvoice", help="TTS provider (cosyvoice, fishspeech, piper)")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    # Determine output path
    output_path = args.output or f"data/test_voices/{args.persona}_test.wav"

    # Synthesize
    success = await synthesize_and_save(
        persona_name=args.persona,
        text=args.text,
        output_path=output_path,
        tts_client=args.tts,
    )

    if success:
        logger.info(f"Voice test complete. Listen to: {output_path}")
    else:
        logger.error("Voice test failed")

    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
