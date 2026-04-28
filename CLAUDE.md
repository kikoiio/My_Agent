# Project: Multi-Persona Voice AI Agent

## Overview

Voice-enabled AI agent platform with multiple personas. Runs 24/7 on Raspberry Pi 4B (edge: wake word, face/voice biometrics, STT/TTS) with a backend server (LLM routing via LiteLLM, 3-tier SQLite memory, LangGraph orchestration, tool calling, security guard, observability). Edge and backend communicate over WireGuard VPN. 89 files, 176 smoke tests passing. Tool calling against real AIHubMix verified end-to-end (2026-04-27).

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

**Required for live run:** `backend/secrets/llm_keys.env` (AIHUBMIX_API_KEY, NVIDIA_API_KEY), Raspberry Pi 4B hardware for edge features.

## Architecture

```
edge/ (Raspberry Pi)          backend/ (Server)
  wakeword.py                    orchestrator/graph.py (LangGraph: draft→critic→respond)
  face_gate.py                   litellm/client.py (model routing)
  voiceprint.py                  memory/store.py (L1/L2/L3)
  audio_routing.py               security/guard.py + ratelimit.py
       │                         observe/tracer.py + dashboard.py
       │ WireGuard VPN           mcp_servers/* (7 tools)
       └──────────────────────── eval/ (judge ensemble + calibration)
              core/ (shared types, router, breaker, persona loading)
              personas/ (persona definitions: template + assistant)
```

**Data flow:** Voice → Pipecat STT → LangGraph (draft → critic → respond) → LiteLLM → TTS → Voice. Memory writes happen after each turn (L2 episodic), with async consolidation to L3 dreams.

## Module Map

| Module | Purpose | Key File |
|--------|---------|----------|
| `core/` | Shared types, persona loading, router, circuit breaker, HAL | `types.py`, `persona.py`, `router.py`, `breaker.py` |
| `backend/litellm/` | LLM client factory, model routing config | `client.py`, `router.yaml` |
| `backend/memory/` | 3-tier SQLite memory (L1/L2/L3) | `store.py`, `dream.py` |
| `backend/orchestrator/` | LangGraph reasoning pipeline + tool calling | `graph.py`, `tools.py` |
| `backend/security/` | Injection guard, rate limiting | `guard.py`, `ratelimit.py` |
| `backend/observe/` | Distributed tracing, dashboard | `tracer.py`, `dashboard.py` |
| `backend/mcp_servers/` | 7 MCP tool implementations | `caldav.py`, `bilibili.py`, `memory.py`, etc. |
| `backend/eval/` | 5-judge ensemble, calibration | `judge_ensemble.py`, `calibration.py` |
| `edge/` | Pi wake word, face/voice biometrics | `wakeword.py`, `face_gate.py` |
| `personas/` | Persona definitions (5 files each) | `_template/`, `assistant/` |
| `eval/` | YAML test cases, harness, reporter | `cases/`, `runners/harness.py` |
| `deploy/` | Docker Compose, systemd, WireGuard | `docker-compose.yml` |
| `tests/` | 176 smoke tests (4 tiers) | `smoke_test.py` |

## Key Conventions

- `from __future__ import annotations` in every Python file
- **SQLite-first** persistence — WAL mode, FTS5 full-text search, no external DB required
- **Pydantic v2** for validated schemas (`.model_dump()`, `.model_validate()`), `dataclasses` for internal structs
- **async throughout** — all I/O uses asyncio
- **Bilingual**: code identifiers in English, comments/docs mixed Chinese/English
- Tests: class-per-component (`TestMemoryStore`, `TestSecurityGuard`), inline imports, `tmp_path` for DB isolation
- Mock LLMs: `lambda system, user_msg, persona=None: "response"`
- Commit messages: Chinese `主题：详情` format
- `plan.md` is the authoritative design document (500+ lines)

## Session Rules

1. **Read this file first** every session
2. **Then read `docs/project-memory.md`** for decisions, pitfalls, and recent changes
3. **Do NOT scan the entire repo** — load files only as needed
4. **Prefer minimal changes** — do not refactor unless asked
5. **Follow existing style** — match the patterns described above
6. **After each task, update `docs/project-memory.md`** with new decisions, pitfalls, or changed context
