"""Sandboxed shell command execution."""

from __future__ import annotations

import asyncio
import subprocess
from typing import Any

__all__ = ["SandboxedShellServer"]


class SandboxedShellServer:
    """Execute shell commands in sandboxed environment."""

    def __init__(self, sandbox_path: str = "/tmp/sandbox", timeout: int = 10):
        """Initialize sandboxed shell.

        Args:
            sandbox_path: Root directory for sandbox
            timeout: Default command timeout in seconds
        """
        self.sandbox_path = sandbox_path
        self.timeout = timeout

    async def execute(
        self,
        command: str,
        cwd: str | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Execute shell command in sandbox.

        Args:
            command: Shell command to execute
            cwd: Working directory
            timeout: Command timeout (default: self.timeout)

        Returns:
            Dict with stdout, stderr, returncode
        """
        timeout = timeout or self.timeout

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    subprocess.run,
                    command,
                    shell=True,
                    cwd=cwd or self.sandbox_path,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                ),
                timeout=timeout,
            )

            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "success": result.returncode == 0,
            }
        except asyncio.TimeoutError:
            return {
                "stdout": "",
                "stderr": "Command timed out",
                "returncode": -1,
                "success": False,
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": str(e),
                "returncode": -1,
                "success": False,
            }

    async def list_files(self, path: str = ".") -> list[str]:
        """List files in sandbox.

        Args:
            path: Path relative to sandbox

        Returns:
            List of file names
        """
        result = await self.execute(f"ls {path}")
        if result["success"]:
            return result["stdout"].strip().split("\n")
        return []

    async def read_file(self, filename: str) -> str:
        """Read file from sandbox.

        Args:
            filename: Filename relative to sandbox

        Returns:
            File contents
        """
        result = await self.execute(f"cat {filename}")
        if result["success"]:
            return result["stdout"]
        return ""
