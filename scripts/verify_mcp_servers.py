#!/usr/bin/env python3
"""直连 MCP server 实例验证凭据 —— 跳过 agent / LLM，只测 cookie 是否真正可用。

跑：python scripts/verify_mcp_servers.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


async def check_pyncm() -> None:
    from backend.mcp_servers.pyncm import PyncmServer

    cred = os.environ.get("NCM_CREDENTIAL_FILE", "backend/secrets/pyncm_credential.json")
    srv = PyncmServer(credential_file=cred)
    print(f"\n[pyncm] credential_file={cred}, authenticated={srv.authenticated}")
    if not srv.authenticated:
        print("[pyncm] SKIP — credential not loaded")
        return

    results = await srv.search_track("七里香", limit=3)
    print(f"[pyncm] search_track('七里香') → {len(results)} hits")
    for r in results:
        print(f"        {r}")


async def check_bilibili() -> None:
    from backend.mcp_servers.bilibili import BilibiliServer

    cred = os.environ.get("BILIBILI_CREDENTIAL_FILE", "backend/secrets/bilibili_credential.json")
    srv = BilibiliServer(credential_file=cred)
    print(f"\n[bilibili] credential_file={cred}, authenticated={srv.authenticated}")
    if not srv.authenticated:
        print("[bilibili] SKIP — credential not loaded")
        return

    # 1 号房 = B 站官方房间，必存在
    info = await srv.get_room_info(1)
    print(f"[bilibili] get_room_info(1) → {info}")


async def main() -> None:
    await check_pyncm()
    await check_bilibili()


if __name__ == "__main__":
    asyncio.run(main())
