#!/usr/bin/env python3
"""生成网易云 pyncm session 凭据。

支持两种取 cookie 的方式：

  方法 A（推荐）：从 DevTools 手动复制 MUSIC_U cookie 到 accounts.env
                   （NCM_MUSIC_U，可选 NCM_CSRF）。
                   不受网易云 8821 行为验证码风控影响，cookie 约 6 个月有效。

  方法 B：手机号 + 密码走 pyncm.LoginViaCellphone API。
          注意 pyncm 内部自动 md5 password，直接传明文；
          网易云对账密登录有风控，首次登录大概率撞 code 8821。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

__all__ = ["main"]

logger = logging.getLogger(__name__)


def _load_env() -> None:
    """Load backend/secrets/accounts.env, with a fallback parser when dotenv missing."""
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

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    logger.info(f"Loaded env from {env_path} (fallback parser)")


def _build_session_from_cookie(music_u: str, csrf: str) -> dict:
    """方法 A：直接构造一个带 MUSIC_U 的 pyncm session 并 dump。"""
    try:
        from pyncm import GetCurrentSession
    except ImportError as e:
        raise RuntimeError("pyncm not installed. Run: pip install pyncm") from e

    sess = GetCurrentSession()
    # pyncm 的 session 是 requests.Session 的子类，cookies 接口一致
    sess.cookies.set("MUSIC_U", music_u, domain=".music.163.com")
    if csrf:
        sess.cookies.set("__csrf", csrf, domain=".music.163.com")
        # 部分 EAPI 调用读 session.csrf_token 而不是 cookie；显式设上更稳
        if hasattr(sess, "csrf_token"):
            sess.csrf_token = csrf

    return sess.dump()


def _login_via_cellphone(phone: str, password: str, country_code: str) -> dict:
    """方法 B：账密登录。"""
    try:
        from pyncm import GetCurrentSession
        from pyncm.apis.login import LoginViaCellphone
    except ImportError as e:
        raise RuntimeError("pyncm not installed. Run: pip install pyncm") from e

    # 直接传明文 password — pyncm 内部 md5
    result = LoginViaCellphone(phone=phone, password=password, ctcode=country_code)
    code = result.get("code")
    if code != 200:
        msg = result.get("message") or result.get("msg") or str(result)
        raise RuntimeError(f"Login failed (code={code}): {msg}")

    return GetCurrentSession().dump()


def _verify(session_data: dict) -> tuple[bool, str]:
    """Hit login-status endpoint to confirm the cookie is alive."""
    try:
        from pyncm import Session, SetCurrentSession
        from pyncm.apis.login import GetCurrentLoginStatus
    except ImportError as e:
        return False, f"pyncm import failed: {e!r}"

    try:
        sess = Session()
        sess.load(session_data)
        SetCurrentSession(sess)
        info = GetCurrentLoginStatus()
        if info.get("code") != 200:
            return False, f"GetCurrentLoginStatus returned: {info}"
        # pyncm 不同版本结构略不同：data.account / data.profile 或顶层 account / profile
        data = info.get("data") or info
        profile = data.get("profile") or {}
        account = data.get("account") or {}
        if not profile and not account:
            return False, "no profile/account in response (cookie likely expired)"
        uid = profile.get("userId") or account.get("id")
        nickname = profile.get("nickname") or "<no nickname>"
        return True, f"uid={uid}, nickname={nickname}"
    except Exception as e:
        return False, f"verification failed: {e!r}"


def _save(session_data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(session_data, ensure_ascii=False), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    logger.info(f"Saved pyncm session to {path}")


def main() -> bool:
    parser = argparse.ArgumentParser(description="Build pyncm session credential")
    parser.add_argument("--output", default=None, help="Override credential output path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    _load_env()

    out_path = Path(
        args.output
        or os.environ.get("NCM_CREDENTIAL_FILE", "backend/secrets/pyncm_credential.json")
    )

    music_u = os.environ.get("NCM_MUSIC_U", "").strip()
    csrf = os.environ.get("NCM_CSRF", "").strip()

    # 方法 A 优先
    if music_u:
        logger.info("Using manual MUSIC_U cookie from env (method A)")
        try:
            session_data = _build_session_from_cookie(music_u, csrf)
        except RuntimeError as e:
            logger.error(str(e))
            return False
    else:
        # 方法 B 回退
        phone = os.environ.get("NCM_PHONE", "").strip()
        password = os.environ.get("NCM_PASSWORD", "")
        country_code = os.environ.get("NCM_COUNTRY_CODE", "86").strip()

        if not phone or not password:
            logger.error(
                "Neither NCM_MUSIC_U nor NCM_PHONE/NCM_PASSWORD set. "
                "Configure backend/secrets/accounts.env (method A 推荐)."
            )
            return False

        logger.info(f"Logging in via cellphone {phone[:3]}***{phone[-2:]}, ctcode={country_code} (method B)")
        try:
            session_data = _login_via_cellphone(phone, password, country_code)
        except RuntimeError as e:
            logger.error(str(e))
            logger.error(
                "Tip: 网易云对账密登录有行为验证码风控（code 8821）。"
                "请改用 method A — 在浏览器登录 music.163.com 后从 DevTools "
                "复制 MUSIC_U cookie 到 accounts.env。"
            )
            return False
        except Exception as e:
            logger.error(f"Unexpected login error: {e!r}")
            return False

    _save(session_data, out_path)

    ok, msg = _verify(session_data)
    if ok:
        logger.info(f"Credential verified: {msg}")
        return True
    # 校验失败不视为 fatal：cookie 文件已经存好，读类 API（search/playlist）通常 MUSIC_U 一个就够。
    # 校验路径走 EAPI，需要 __csrf 才能正确签名；没填就会撞解密报错，但运行时未必有问题。
    logger.warning(f"Credential saved to {out_path} but auto-verification failed: {msg}")
    logger.warning(
        "这通常是 EAPI 签名缺 __csrf。读类 API（搜歌、查歌单）有 MUSIC_U 一个 cookie 就够，"
        "建议直接通过 agent 跑一次搜索验证。如要消除此警告，把 __csrf cookie 也填进 NCM_CSRF。"
    )
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
