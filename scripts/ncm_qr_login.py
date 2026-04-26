#!/usr/bin/env python3
"""QR code login for Netease Cloud Music account.

Per plan.md §11.7: Authenticate with Netease Cloud Music using QR code.
"""

import argparse
import asyncio
import json
import logging
from pathlib import Path

__all__ = ["main"]

logger = logging.getLogger(__name__)


async def get_qr_code() -> dict[str, str]:
    """Get QR code for NCM login.

    Returns:
        Dict with 'qrcode_url' and 'qrcode_key'
    """
    try:
        # Placeholder: would use pyncm
        # from pyncm import QrcodeLogin
        # qr_login = QrcodeLogin()
        # qr_info = qr_login.get_qrcode()

        return {
            "qrcode_url": "https://example.com/qrcode.png",
            "qrcode_key": "ncm_qr_12345",
        }
    except Exception as e:
        logger.error(f"Failed to get QR code: {e}")
        return {}


async def wait_for_scan(qrcode_key: str, timeout_s: int = 120) -> dict[str, str] | None:
    """Wait for QR code to be scanned.

    Args:
        qrcode_key: QR code key
        timeout_s: Timeout in seconds

    Returns:
        Credential dict if scanned, None if timeout
    """
    import time

    logger.info("Waiting for QR code scan...")
    start_time = time.time()

    while time.time() - start_time < timeout_s:
        try:
            # Placeholder: would poll status
            # status = check_qr_status(qrcode_key)
            # if status.get('status') == 'confirmed':
            #     return status.get('credential')

            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Scan check failed: {e}")

    logger.warning("QR code scan timeout")
    return None


async def save_credential(credential: dict[str, str]) -> bool:
    """Save NCM credential to file.

    Args:
        credential: Credential dict

    Returns:
        True if saved successfully
    """
    cred_path = Path("backend/secrets/ncm_credential.json")
    cred_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Mask sensitive data in logs
        masked = {k: ("***" if k in ["cookie", "token"] else v) for k, v in credential.items()}
        logger.info(f"Saving credential: {masked}")

        cred_path.write_text(json.dumps(credential), encoding="utf-8")
        cred_path.chmod(0o600)

        logger.info(f"Credential saved to: {cred_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save credential: {e}")
        return False


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Netease Cloud Music QR login")
    parser.add_argument("--timeout", type=int, default=120, help="QR scan timeout (seconds)")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    # Get QR code
    qr_info = await get_qr_code()
    if not qr_info:
        logger.error("Failed to get QR code")
        return False

    logger.info(f"Scan this QR code: {qr_info['qrcode_url']}")

    # Wait for scan
    credential = await wait_for_scan(qr_info["qrcode_key"], timeout_s=args.timeout)
    if not credential:
        logger.error("QR code scan failed or timed out")
        return False

    # Save credential
    success = await save_credential(credential)
    if success:
        logger.info("Netease Cloud Music login successful")
    else:
        logger.error("Failed to save credential")

    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
