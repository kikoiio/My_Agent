#!/usr/bin/env python3
"""导入 B 站 cookie，生成可被 bilibili-api-python 使用的凭据 JSON。

替代原 QR 扫码方案 —— 扫码登录被风控，密码登录被极验滑块拦截。
脚本支持两种取 cookie 的方式：

  方法 A（推荐）：从 DevTools 手动复制 4 个 cookie 到 accounts.env
                   （BILIBILI_SESSDATA / BILIBILI_BILI_JCT /
                    BILIBILI_BUVID3 / BILIBILI_DEDEUSERID）。
                   零依赖，不受浏览器加密升级影响。

  方法 B：用 browser-cookie3 自动从浏览器 cookie 库读。
          注意 Edge / Chrome 自 2024 年起启用 App-Bound Encryption，
          解密大概率失败；Firefox 仍可用。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

__all__ = ["main"]

logger = logging.getLogger(__name__)

REQUIRED_COOKIES = ("SESSDATA", "bili_jct", "buvid3", "DedeUserID")

# 方法 A：env 变量名 → 内部 credential 字段名
ENV_COOKIE_MAP = {
    "BILIBILI_SESSDATA": "sessdata",
    "BILIBILI_BILI_JCT": "bili_jct",
    "BILIBILI_BUVID3": "buvid3",
    "BILIBILI_DEDEUSERID": "dedeuserid",
}


def _load_env() -> None:
    """Load backend/secrets/accounts.env into os.environ.

    Prefers python-dotenv; falls back to a minimal hand-rolled parser so the
    script keeps working in venvs that haven't run `pip install -r requirements.txt` yet.
    """
    env_path = Path("backend/secrets/accounts.env")
    if not env_path.exists():
        logger.warning(f"{env_path} not found; relying on existing env vars")
        return

    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
        logger.info(f"Loaded env from {env_path}")
        return
    except ImportError:
        pass

    # Minimal fallback parser
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)
    logger.info(f"Loaded env from {env_path} (fallback parser; install python-dotenv for full support)")


def _try_manual_cookies() -> dict[str, str] | None:
    """Read 4 cookies from env vars (方法 A). Return None if any are missing."""
    out: dict[str, str] = {}
    for env_name, field in ENV_COOKIE_MAP.items():
        v = os.environ.get(env_name, "").strip()
        if not v:
            return None
        out[field] = v
    return out


def _extract_cookies(browser: str, profile: str | None) -> dict[str, str]:
    """Extract bilibili cookies from the named browser's cookie store.

    Args:
        browser: edge / chrome / firefox / brave / chromium
        profile: Optional profile directory path; None for default

    Returns:
        Dict of cookie name → value, restricted to REQUIRED_COOKIES.
    """
    try:
        import browser_cookie3
    except ImportError as e:
        raise RuntimeError(
            "browser-cookie3 not installed. Run: pip install browser-cookie3"
        ) from e

    loader = getattr(browser_cookie3, browser.lower(), None)
    if loader is None:
        raise ValueError(
            f"Unsupported browser: {browser!r}. "
            f"Supported: edge, chrome, firefox, brave, chromium"
        )

    kwargs: dict[str, str] = {"domain_name": "bilibili.com"}
    if profile:
        kwargs["cookie_file"] = profile

    jar = loader(**kwargs)

    found: dict[str, str] = {}
    for cookie in jar:
        if cookie.name in REQUIRED_COOKIES:
            found[cookie.name] = cookie.value

    return found


def _build_credential(cookies: dict[str, str]) -> dict[str, str]:
    """Map raw cookie names → bilibili-api-python Credential field names."""
    return {
        "sessdata": cookies["SESSDATA"],
        "bili_jct": cookies["bili_jct"],
        "buvid3": cookies["buvid3"],
        "dedeuserid": cookies["DedeUserID"],
    }


def _register_http_client() -> None:
    """bilibili-api-python v17+ 把 HTTP 客户端做成可插拔，需要显式注册一个。

    我们的 requirements.txt 已经装了 aiohttp，优先用它；都失败就让调用方处理。
    """
    try:
        import bilibili_api  # type: ignore
    except ImportError:
        return

    for impl in ("aiohttp", "httpx", "curl_cffi"):
        select_client = getattr(bilibili_api, "select_client", None)
        if callable(select_client):
            try:
                select_client(impl)
                return
            except Exception:
                pass

        rs = getattr(bilibili_api, "request_settings", None)
        if rs is not None:
            try:
                if hasattr(rs, "set_impl"):
                    rs.set_impl(impl)
                    return
                if hasattr(rs, "set"):
                    rs.set("impl", impl)
                    return
            except Exception:
                continue


async def _verify(credential: dict[str, str]) -> tuple[bool, str]:
    """Verify cookies are live by hitting B 站 user info API."""
    try:
        from bilibili_api import Credential, user
    except ImportError:
        return False, "bilibili-api-python not installed (pip install bilibili-api-python)"

    _register_http_client()

    try:
        cred = Credential(**credential)
        uid = int(credential["dedeuserid"])
        info = await user.User(uid, credential=cred).get_user_info()
        uname = info.get("name", "<unknown>")
        return True, f"uid={uid}, name={uname}"
    except Exception as e:
        return False, f"verification failed: {e!r}"


def _save(credential: dict[str, str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(credential), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass  # Windows 上 chmod 是软约定

    masked = {
        k: ("***" + v[-4:] if k in ("sessdata", "bili_jct") and len(v) > 4 else v)
        for k, v in credential.items()
    }
    logger.info(f"Saved credential to {path}: {masked}")


async def main() -> bool:
    parser = argparse.ArgumentParser(description="Import bilibili cookies from local browser")
    parser.add_argument(
        "--browser",
        default=None,
        help="Override BILIBILI_BROWSER env (edge/chrome/firefox/brave/chromium)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Override credential output path",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    _load_env()

    out_path = Path(
        args.output
        or os.environ.get("BILIBILI_CREDENTIAL_FILE", "backend/secrets/bilibili_credential.json")
    )

    # 方法 A：先看 env 里有没有手动粘贴的 4 个 cookie
    credential = _try_manual_cookies()
    if credential is not None:
        logger.info("Using manual cookies from env (method A)")
    else:
        # 方法 B：browser-cookie3 自动读浏览器 cookie 库
        browser = args.browser or os.environ.get("BILIBILI_BROWSER", "firefox")
        profile = os.environ.get("BILIBILI_BROWSER_PROFILE") or None
        logger.info(f"Reading {browser} cookies (profile={profile or 'default'}) — method B")

        try:
            cookies = _extract_cookies(browser, profile)
        except Exception as e:
            logger.error(f"Failed to read browser cookies: {e}")
            logger.error(
                "Tip: Edge/Chrome 2024+ 启用 App-Bound Encryption，browser-cookie3 解不开。"
                " 请改用 method A（在 accounts.env 中填 4 个 BILIBILI_* cookie），"
                " 详见 backend/secrets/accounts.env.example。"
            )
            return False

        missing = [name for name in REQUIRED_COOKIES if name not in cookies]
        if missing:
            logger.error(
                f"Missing cookies {missing}. "
                f"Please log in to bilibili.com in {browser} first, then retry."
            )
            return False

        credential = _build_credential(cookies)

    _save(credential, out_path)

    ok, msg = await _verify(credential)
    if ok:
        logger.info(f"Credential verified: {msg}")
        return True
    logger.error(f"Credential saved but verification failed: {msg}")
    return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
