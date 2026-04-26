"""N concurrent wake word listeners (openwakeword + ONNX)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

__all__ = ["WakeWordListener"]

logger = logging.getLogger(__name__)


class WakeWordListener:
    """Single wake word detector instance."""

    def __init__(
        self,
        persona: str,
        model_path: str | None = None,
        threshold: float = 0.5,
    ):
        """Initialize wake word listener.

        Args:
            persona: Persona name (used as wake word trigger)
            model_path: Path to ONNX model
            threshold: Confidence threshold
        """
        self.persona = persona
        self.model_path = model_path
        self.threshold = threshold
        self.model = None
        self.running = False

    async def load_model(self) -> bool:
        """Load ONNX model for this persona.

        Returns:
            True if loaded successfully
        """
        try:
            # Placeholder: would use openwakeword
            # from openwakeword.model import Model
            # self.model = Model(
            #     wakeword_models=[self.model_path],
            #     ...
            # )

            logger.info(f"Loaded wake word model for: {self.persona}")
            return True
        except Exception as e:
            logger.error(f"Failed to load model for {self.persona}: {e}")
            return False

    async def listen(self, audio_stream: Any) -> Any:
        """Listen for wake word in audio stream.

        Args:
            audio_stream: Async generator of audio chunks

        Yields:
            (persona, confidence) when wake word detected
        """
        if not self.model:
            await self.load_model()

        self.running = True
        try:
            async for audio_chunk in audio_stream:
                # Placeholder: would process audio chunk through ONNX model
                # prediction = self.model.predict(audio_chunk)
                # if prediction.scores[self.persona] > self.threshold:
                #     yield (self.persona, prediction.scores[self.persona])

                # Dummy: never triggers
                pass
        finally:
            self.running = False

    async def stop(self) -> None:
        """Stop listening."""
        self.running = False


class MultiWakeWordListener:
    """Manage N concurrent wake word listeners."""

    def __init__(self, personas: list[str]):
        """Initialize multi-listener.

        Args:
            personas: List of persona names
        """
        self.personas = personas
        self.listeners = {
            persona: WakeWordListener(persona) for persona in personas
        }
        self.listen_tasks = []

    async def start_listeners(self, audio_stream: Any) -> None:
        """Start all listeners on shared audio stream.

        Args:
            audio_stream: Async generator of audio frames
        """
        # Create task for each listener
        for persona, listener in self.listeners.items():
            task = asyncio.create_task(
                self._listener_loop(listener, audio_stream)
            )
            self.listen_tasks.append(task)

        logger.info(f"Started {len(self.listeners)} wake word listeners")

    async def _listener_loop(self, listener: WakeWordListener, audio_stream: Any) -> None:
        """Single listener event loop.

        Args:
            listener: WakeWordListener instance
            audio_stream: Shared audio stream
        """
        try:
            async for persona, confidence in listener.listen(audio_stream):
                logger.info(f"Wake word detected: {persona} (confidence={confidence:.2f})")
                # Would emit event here
        except Exception as e:
            logger.error(f"Listener error for {listener.persona}: {e}")

    async def stop_all(self) -> None:
        """Stop all listeners."""
        for listener in self.listeners.values():
            await listener.stop()

        # Cancel all tasks
        for task in self.listen_tasks:
            task.cancel()

        try:
            await asyncio.gather(*self.listen_tasks)
        except asyncio.CancelledError:
            pass

        logger.info("All wake word listeners stopped")

    async def get_active_listeners(self) -> list[str]:
        """Get currently active listener personas."""
        return [p for p, l in self.listeners.items() if l.running]
