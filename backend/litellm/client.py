"""LiteLLM client factory — loads router.yaml and creates llm_call callables."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable

import yaml
from dotenv import load_dotenv

from core.persona import Persona

_ENV_LOADED = False
_ROUTER_CONFIG: dict[str, Any] | None = None


def _load_env() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    env_path = Path(__file__).resolve().parent.parent / "secrets" / "llm_keys.env"
    if env_path.exists():
        load_dotenv(env_path)
    _ENV_LOADED = True


def _resolve_env(value: str) -> str:
    """Replace ${VAR} placeholders with environment variable values."""
    pattern = re.compile(r"\$\{(\w+)\}")

    def _replacer(m: re.Match) -> str:
        return os.environ.get(m.group(1), "")

    return pattern.sub(_replacer, value)


def load_router_config() -> dict[str, Any]:
    global _ROUTER_CONFIG
    if _ROUTER_CONFIG is not None:
        return _ROUTER_CONFIG

    _load_env()
    config_path = Path(__file__).resolve().parent / "router.yaml"
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # Resolve env vars in model_list
    for entry in raw.get("model_list", []):
        params = entry.get("litellm_params", {})
        if "api_key" in params:
            params["api_key"] = _resolve_env(params["api_key"])

    _ROUTER_CONFIG = raw
    return raw


def _build_model_map() -> dict[str, dict[str, Any]]:
    config = load_router_config()
    model_map: dict[str, dict[str, Any]] = {}
    for entry in config.get("model_list", []):
        name = entry["model_name"]
        params = entry["litellm_params"]
        model_map[name] = {
            "model": params["model"],
            "api_base": params.get("api_base", ""),
            "api_key": params.get("api_key", ""),
            "temperature": entry.get("temperature", 0.7),
            "max_input": entry.get("max_input", 8000),
            "max_output": entry.get("max_output", 2000),
        }
    return model_map


def create_llm_callable(role: str = "default_fast") -> Callable[[str, str, Persona], str]:
    """Create an llm_call function bound to a specific model role.

    Returns a callable matching the signature expected by core.loop.agent_loop:
        (system_prompt: str, user_msg: str, persona: Persona) -> str
    """
    model_map = _build_model_map()
    cfg = model_map.get(role, model_map.get("default_fast", {}))

    if not cfg:
        raise ValueError(f"No model config found for role '{role}'")

    model_name = cfg["model"]
    api_base = cfg["api_base"]
    api_key = cfg["api_key"]
    temperature = cfg["temperature"]

    # Determine provider prefix for litellm
    if api_base and "nvidia" in api_base.lower():
        litellm_model = f"nvidia/{model_name}"
    elif api_base and "aihubmix" in api_base.lower():
        litellm_model = f"openai/{model_name}"
    else:
        litellm_model = model_name

    def llm_call(system_prompt: str, user_msg: str, persona: Persona) -> str:
        import litellm

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]

        response = litellm.completion(
            model=litellm_model,
            messages=messages,
            api_base=api_base,
            api_key=api_key,
            temperature=temperature,
            max_tokens=cfg["max_output"],
            timeout=30,
        )

        return response.choices[0].message.content or ""

    return llm_call


def get_llm_callable_for_route(routed_role: str) -> Callable[[str, str, Persona], str]:
    """Map a router.py role string to the appropriate model and return callable.

    Maps: default_fast|default_smart|cheap|vision|long_context → model
    """
    return create_llm_callable(role=routed_role)
