"""Remote hardware interface (Pi proxied via WebSocket).

Per plan.md §12.2: Backend calls Pi via Pipecat WebSocket proxy.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from core.hardware.base import HardwareInterface
from core.types import CaptureResult, AudioResult, WakeEvent

__all__ = ["RemoteHardware"]

logger = logging.getLogger(__name__)


class RemoteHardware(HardwareInterface):
    """Hardware interface that proxies to remote Pi via WebSocket."""

    def __init__(self, ws_url: str = "ws://raspberrypi.local:8000/hardware"):
        """Initialize remote hardware.

        Args:
            ws_url: WebSocket URL of Pi hardware service
        """
        self.ws_url = ws_url
        self.ws_connection = None

    async def connect(self) -> bool:
        """Connect to remote Pi.

        Returns:
            True if connected
        """
        try:
            import websockets

            self.ws_connection = await websockets.connect(self.ws_url)
            logger.info(f"Connected to remote hardware at {self.ws_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to remote hardware: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from remote Pi."""
        if self.ws_connection:
            await self.ws_connection.close()

    async def _send_command(self, command: str, **kwargs) -> dict[str, Any]:
        """Send RPC command to Pi.

        Args:
            command: Command name
            **kwargs: Command parameters

        Returns:
            Response dict
        """
        if not self.ws_connection:
            return {"error": "Not connected"}

        try:
            payload = json.dumps({"command": command, "args": kwargs})
            await self.ws_connection.send(payload)

            # Wait for response
            response_str = await asyncio.wait_for(
                self.ws_connection.recv(), timeout=10
            )
            return json.loads(response_str)
        except Exception as e:
            logger.error(f"RPC error: {e}")
            return {"error": str(e)}

    async def capture_image(self) -> CaptureResult:
        """Request image capture from remote Pi."""
        response = await self._send_command("capture_image")

        if "error" in response:
            return CaptureResult(image_bytes=None, width=0, height=0, error=response["error"])

        return CaptureResult(
            image_bytes=response.get("image_bytes", b"").encode(),
            width=response.get("width", 0),
            height=response.get("height", 0),
        )

    async def capture_audio(self, duration_s: float = 5.0) -> AudioResult:
        """Request audio capture from remote Pi."""
        response = await self._send_command("capture_audio", duration_s=duration_s)

        if "error" in response:
            return AudioResult(
                audio_bytes=None,
                transcript=None,
                duration_s=0,
                error=response["error"],
            )

        return AudioResult(
            audio_bytes=response.get("audio_bytes", b"").encode(),
            transcript=response.get("transcript"),
            duration_s=response.get("duration_s", 0),
        )

    def stream_wake_events(self) -> Any:
        """Stream wake events from remote Pi.

        Note: This is a generator, not async.
        """
        # Placeholder: would establish persistent WebSocket connection
        # and yield WakeEvent as they arrive

        async def _stream():
            if not await self.connect():
                return

            try:
                while True:
                    response_str = await self.ws_connection.recv()
                    event_data = json.loads(response_str)

                    if event_data.get("type") == "wake_event":
                        yield WakeEvent(
                            persona=event_data["persona"],
                            confidence=event_data["confidence"],
                            ts=event_data["timestamp"],
                        )
            except Exception as e:
                logger.error(f"Wake stream error: {e}")
            finally:
                await self.disconnect()

        # Return async generator wrapped in sync generator
        return _stream()

    async def verify_face(self, image_bytes: bytes, owner_id: str) -> bool:
        """Request face verification from remote Pi."""
        response = await self._send_command(
            "verify_face",
            image_bytes=image_bytes.hex(),
            owner_id=owner_id,
        )
        return response.get("verified", False)

    async def verify_voice(self, audio_bytes: bytes, owner_id: str) -> bool:
        """Request voice verification from remote Pi."""
        response = await self._send_command(
            "verify_voice",
            audio_bytes=audio_bytes.hex(),
            owner_id=owner_id,
        )
        return response.get("verified", False)

    async def play_audio(self, audio_bytes: bytes) -> bool:
        """Request audio playback on remote Pi."""
        response = await self._send_command(
            "play_audio",
            audio_bytes=audio_bytes.hex(),
        )
        return response.get("success", False)
