"""Edge runtime: Pi asyncio event loop + Pipecat WebSocket client.

Per plan.md §12.1: Orchestrates Pi sensors and acts as Pipecat client.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

__all__ = ["EdgeRuntime"]

logger = logging.getLogger(__name__)


class EdgeRuntime:
    """Main event loop for Pi edge device."""

    def __init__(
        self,
        backend_url: str = "ws://192.168.1.100:8000",
        config_path: Path | str = "config.yaml",
    ):
        """Initialize edge runtime.

        Args:
            backend_url: Backend WebSocket URL
            config_path: Path to config file
        """
        self.backend_url = backend_url
        self.config_path = Path(config_path)
        self.running = False

    async def setup(self) -> None:
        """Initialize hardware and connect to backend."""
        logger.info("Edge runtime starting...")

        # Load config
        if self.config_path.exists():
            import yaml

            config = yaml.safe_load(self.config_path.read_text())
            logger.info(f"Loaded config: {config}")

        # Initialize hardware
        try:
            from core.hardware.rpi import RPiHardware

            self.hardware = RPiHardware()
            logger.info("Pi hardware initialized")
        except Exception as e:
            logger.error(f"Hardware init failed: {e}")
            self.hardware = None

        # Start wake word listeners
        await self._start_wake_listeners()

        logger.info("Edge runtime ready")

    async def _start_wake_listeners(self) -> None:
        """Start N concurrent wake word listeners."""
        if not self.hardware:
            logger.warning("No hardware, skipping wake listeners")
            return

        # Placeholder: would start multiple openwakeword listeners
        # for persona in persona_list:
        #     task = asyncio.create_task(listen_wake_word(persona))

        logger.info("Wake word listeners started")

    async def main_loop(self) -> None:
        """Main event loop: connect to backend, stream audio."""
        self.running = True

        try:
            import websockets
            import json

            async with websockets.connect(self.backend_url) as ws:
                logger.info(f"Connected to backend: {self.backend_url}")

                while self.running:
                    try:
                        # Listen for commands from backend
                        message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        command = json.loads(message)
                        await self._handle_command(command, ws)

                    except asyncio.TimeoutError:
                        # No command, idle
                        pass
                    except Exception as e:
                        logger.error(f"Command handling error: {e}")

        except Exception as e:
            logger.error(f"Backend connection error: {e}")

    async def _handle_command(self, command: dict, ws) -> None:
        """Handle command from backend.

        Args:
            command: Command dict
            ws: WebSocket connection
        """
        cmd_type = command.get("type")
        logger.info(f"Received command: {cmd_type}")

        if cmd_type == "capture_image":
            if self.hardware:
                result = await self.hardware.capture_image()
                await ws.send(
                    json.dumps(
                        {
                            "type": "image_result",
                            "image_bytes": result.image_bytes.hex() if result.image_bytes else None,
                            "width": result.width,
                            "height": result.height,
                        }
                    )
                )

        elif cmd_type == "play_audio":
            audio_bytes = bytes.fromhex(command.get("audio_bytes", ""))
            if self.hardware:
                success = await self.hardware.play_audio(audio_bytes)
                await ws.send(json.dumps({"type": "play_result", "success": success}))

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Edge runtime shutting down...")
        self.running = False

        if hasattr(self, "hardware") and self.hardware:
            await self.hardware.shutdown()

        logger.info("Edge runtime stopped")

    async def run(self) -> None:
        """Run edge runtime."""
        await self.setup()
        await self.main_loop()
        await self.shutdown()


async def main():
    """Entry point."""
    logging.basicConfig(level=logging.INFO)
    runtime = EdgeRuntime()
    await runtime.run()


if __name__ == "__main__":
    asyncio.run(main())
