# Project: Multi-Persona Voice AI Agent

## Overview

Open-source, self-hostable local voice AI companion platform. Runs on a single machine (gaming laptop or desktop): wake word detection, face/voice biometrics, STT/TTS in the edge layer; LLM routing via LiteLLM, 3-tier SQLite memory, LangGraph orchestration, tool calling, security guard, and observability in the backend. No second device or VPN required. 257 smoke tests passing. Tool calling against real AIHubMix verified end-to-end (2026-04-27).

Each persona is a **friend** with an independent name (= wake word), voice (CosyVoice zero-shot clone), personality, and private episodic memory (L2). All personas share a global semantic memory (L3) — things you'd post to "Moments". See `plan.md` for full design.

## Quick Start

```bash
# Install
pip install -r requirements.txt

# CLI chat
python main.py
python main.py --persona assistant

# Tests (no API keys or hardware needed)
python -m pytest tests/smoke_test.py -v

# Specific test categories
python -m pytest tests/smoke_test.py -k "memory" -v
python -m pytest tests/smoke_test.py -k "security" -v

# Docker deployment
docker compose -f deploy/docker-compose.yml up -d
```

**Required for live run:** `backend/secrets/llm_keys.env` (AIHUBMIX_API_KEY, NVIDIA_API_KEY), USB camera + microphone, Bluetooth/USB speaker.

## Architecture

```
单机（游戏本 / 台式机）
  edge/                          backend/
    wakeword.py (呼名触发)           orchestrator/graph.py (LangGraph: draft→critic→respond)
    face_gate.py                    litellm/client.py (model routing)
    voiceprint.py                   memory/store.py (L1/L2/L3)
    audio_routing.py                security/guard.py + ratelimit.py
    emotion.py (声学特征)            observe/tracer.py + dashboard.py
         │                          mcp_servers/* (7 tools)
         │  进程内直接调用            proactive/scanner.py (主动感知)
         └───────────────────────── eval/ (judge ensemble + calibration)
                core/ (shared types, router, breaker, persona loading)
                personas/ (persona definitions: _template + assistant)
```

**Data flow:** Voice → openWakeWord（人格名触发）→ Whisper STT → LangGraph (draft → critic → respond) → LiteLLM → CosyVoice TTS → 音箱。Memory: L2 写入按 persona_id 隔离，L3 全局共享，Dream 异步蒸馏 L2→L3。

## Module Map

| Module | Purpose | Key File |
|--------|---------|----------|
| `core/` | Shared types, persona loading, router, circuit breaker | `types.py`, `persona.py`, `router.py`, `breaker.py` |
| `backend/litellm/` | LLM client factory, model routing config | `client.py`, `router.yaml` |
| `backend/memory/` | 3-tier SQLite memory (L1 global / L2 per-persona / L3 shared) | `store.py`, `dream.py` |
| `backend/orchestrator/` | LangGraph reasoning pipeline + tool calling | `graph.py`, `tools.py` |
| `backend/security/` | Injection guard, rate limiting | `guard.py`, `ratelimit.py` |
| `backend/observe/` | Distributed tracing, dashboard | `tracer.py`, `dashboard.py` |
| `backend/mcp_servers/` | 7 MCP tool implementations | `caldav.py`, `bilibili.py`, `memory.py`, etc. |
| `backend/proactive/` | 定时主动感知扫描器 | `scanner.py`, `triggers.py` |
| `backend/eval/` | 5-judge ensemble, calibration | `judge_ensemble.py`, `calibration.py` |
| `edge/` | 本机感知层：唤醒词、人脸、声纹、音频路由 | `wakeword.py`, `face_gate.py` |
| `core/hardware/` | HAL 抽象层（单机）：base/null/mock | `base.py`, `null.py`, `mock.py` |
| `personas/` | Persona definitions (wake_word + voice_ref + system prompt) | `_template/`, `assistant/`, `xiaolin/` |
| `tools/` | Persona pack/install/validate CLI | `persona_pack.py` |
| `eval/` | YAML test cases, harness, reporter, calibration probes | `cases/`, `runners/harness.py`, `jury/probes/` |
| `deploy/` | Docker Compose, systemd | `docker-compose.yml` |
| `tests/` | 257 smoke tests (4 tiers) | `smoke_test.py` |

## Key Conventions

- `from __future__ import annotations` in every Python file
- **SQLite-first** persistence — WAL mode, FTS5 full-text search, no external DB required
- **Pydantic v2** for validated schemas (`.model_dump()`, `.model_validate()`), `dataclasses` for internal structs
- **async throughout** — all I/O uses asyncio
- **Bilingual**: code identifiers in English, comments/docs mixed Chinese/English
- Tests: class-per-component (`TestMemoryStore`, `TestSecurityGuard`), inline imports, `tmp_path` for DB isolation
- Mock LLMs: `lambda system, user_msg, persona=None: "response"`
- Commit messages: Chinese `主题：详情` format
- `plan.md` is the authoritative design document; `docs/implementation-plan.md` is the phased execution plan (P1–P6)

## Session Rules

1. **Read this file first** every session
2. **Then read `docs/project-memory.md`** for decisions, pitfalls, and recent changes
3. **If asked to implement the project**, read `docs/implementation-plan.md` for the current phase (P1–P6) before touching any code
4. **Do NOT scan the entire repo** — load files only as needed
5. **Prefer minimal changes** — do not refactor unless asked
6. **Follow existing style** — match the patterns described above
7. **After each task, update `docs/project-memory.md`** with new decisions, pitfalls, changed context, smoke test count, roadmap status (P1–P6 ✅/⬜), and a session log entry
