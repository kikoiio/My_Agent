# Architecture: Multi-Persona Voice AI Agent

## System Architecture

Two-tier deployment: **Raspberry Pi 4B edge** handles real-time audio, wake word detection, and biometrics. **Backend server** (laptop/desktop) handles LLM inference, memory, orchestration, and observability. Communication over encrypted WireGuard VPN tunnel.

```
┌─ Raspberry Pi 4B (edge/) ─────────────────────────────────────┐
│  wakeword.py ──► face_gate.py ──► voiceprint.py               │
│  audio_routing.py (PipeWire → BT speaker/mic)                 │
│  pipecat_app.py (STT → LLM → TTS pipeline)                    │
└──────────────────────┬────────────────────────────────────────┘
                       │ WireGuard VPN
┌──────────────────────┴────────────────────────────────────────┐
│  Backend Server (backend/)                                     │
│  orchestrator/graph.py ← litellm/client.py ← aihubmix/nvidia  │
│  memory/store.py (L1→L2→L3)    security/guard.py              │
│  observe/tracer.py              mcp_servers/* (7 tools)       │
└────────────────────────────────────────────────────────────────┘
         shared: core/ (types, router, breaker, persona, HAL)
         config: personas/ (per-persona prompts + tools)
```

---

## Module Deep Dive

### core/ — Platform-Independent Core

**Responsibility:** Shared types, persona loading, message routing, circuit breaker, agent loop, hardware abstraction.

**Key components:**
| File | Key exports | Purpose |
|------|------------|---------|
| `core/types.py` | `Message`, `AgentState`, `ToolResult` | Pydantic/dataclass data models |
| `core/persona.py` | `Persona`, `load()`, `list_personas()` | Persona loading from 5-file directory |
| `core/router.py` | route logic | Chooses LLM model role based on msg length, keywords, images |
| `core/breaker.py` | `CircuitBreaker` | Per-run safety: max 15 steps, duplicate detection via SHA-256 |
| `core/loop.py` | `agent_loop()` | Single-turn: route → LLM → memory → trace |
| `core/hardware/` | `base.py`, `rpi.py`, `mock.py`, `remote.py`, `null.py` | Hardware abstraction layer (HAL) |

**Dependencies:** None internal. Imported by `core/loop.py` and `backend/orchestrator/`.

---

### backend/litellm/ — LLM Routing

**Responsibility:** Abstract LLM calls behind a factory that selects model/provider based on role.

**Key files:**
- `client.py` — `create_llm_callable(role)` returns `Callable[[str,str,Persona], str]`. Loads `router.yaml`, resolves `${ENV_VAR}` placeholders, routes via aihubmix.com or build.nvidia.com.
- `router.yaml` — 7 model slots: `default_fast`, `default_smart`, `cheap`, `vision`, `long_context`, `judge_1..3`. Cost cap 5 RMB/day. Per-role token limits.

**Dependencies:** `core.persona` (Persona type hint), `litellm`, `python-dotenv`.

---

### backend/memory/ — Three-Tier Memory

**Responsibility:** Persistent memory across sessions with full-text search and async consolidation.

**Tiers:**
| Tier | Table | Purpose |
|------|-------|---------|
| L1 | `sessions` | Current conversation buffer, 12K token budget |
| L2 | `episodes` + FTS5 | Full-text searchable episodic memory |
| L3 | `dreams` | Consolidated patterns (preferences, events, habits, relationships, todos) |

**Key files:**
- `store.py` — `MemoryStore` class. All operations thread-safe via `threading.Lock`. WAL mode. FTS5 triggers keep search index in sync.
- `dream.py` — `DreamWorker` async consolidation. Triggers: 30min idle, >20 pending, 3AM cron. Quality-gated at 0.7. Privacy redaction.
- `embedding_provider.py` — `EmbeddingProvider` with fallback (local BGE-M3 → OpenAI API → zero vectors). **Not yet wired to store.py** — search is pure FTS5 text-based.

**Dependencies:** SQLite (stdlib), consumed by `mcp_servers/memory.py`, `dream.py`, `observe/dashboard.py`.

---

### backend/orchestrator/ — LangGraph Reasoning

**Responsibility:** Core agent reasoning loop as a directed graph.

**Key files:**
- `graph.py` — Three-node LangGraph: `draft_node` (LLM generates) → `critic_node` (safety check + persona consistency) → `respond_node` (finalize or suppress). Falls back to sequential dict execution if langgraph unavailable.
- `persona_load.py` — `load_persona_into_graph()` injects persona metadata into graph state.

**Dependencies:** `litellm/client.py` (LLM callables), `security/guard.py` (critic safety check), `core/persona.py`.

---

### backend/security/ — Guard & Rate Limiting

**Key files:**
- `guard.py` — `Guard` class. Wraps external content in XML tags. Detects 5 injection categories (prompt injection, SQLi, XSS, path traversal, command injection). Risk score 0-1, threshold 0.5.
- `ratelimit.py` — `RateLimiter` using atomic SQLite `UPDATE WHERE affected_rows=0`. Supports sliding/fixed windows. `ThrottledCall` context manager.

**Dependencies:** `observe/tracer.py` (rate limit counters live in tracer DB).

---

### backend/observe/ — Tracing & Dashboard

**Key files:**
- `tracer.py` — `Tracer` class. SQLite-backed: traces, spans, events, judge_bank, rate_counters. 90-day retention. Thread-safe.
- `dashboard.py` — `DashboardApp`. FastAPI-based, single-file HTML rendering. Mounts at `127.0.0.1:8080`.

---

### backend/mcp_servers/ — Tool Implementations

Seven MCP servers registered in `nanobot/config.yaml`:

| Server | File | Key Tools |
|--------|------|-----------|
| Bilibili | `bilibili.py` | get_live_chat, send_message |
| Netease Music | `pyncm.py` | search_track, get_playlist |
| Web Search | `bocha_search.py` | bocha_search |
| Browser | `browser_use_wrapper.py` | navigate, click, extract_text |
| Calendar | `caldav.py` | list/create/delete/update events |
| Shell | `sandboxed_shell.py` | shell_execute |
| Memory | `memory.py` | recall, store (wraps MemoryStore) |

`caldav.py` runs blocking CalDAV calls in `ThreadPoolExecutor` to avoid blocking the async event loop.

---

### backend/eval/ — Evaluation Framework

**Key files:**
- `judge_ensemble.py` — 5-judge jury: independent scoring → debate round → weighted aggregation. Thresholds: pass ≥0.6, fail ≤0.4.
- `calibration.py` — `Calibrator`. Gold-standard blind probes. Multiplicative weight update: hit ×1.01, miss ×0.97, clamped [0.5, 1.5].

---

### edge/ — Raspberry Pi Edge Layer

Hardware-dependent. Requires Pi 4B with camera, mic, speaker.
- `wakeword.py` — OpenWakeWord multi-persona detection
- `face_gate.py` — InsightFace enrollment + recognition
- `voiceprint.py` — 3D-Speaker biometric verification
- `audio_routing.py` — PipeWire-based BT audio

---

### personas/ — Persona Definitions

Each persona is a directory with 5 files:
1. `system_prompt.md` — Core behavior and safety rules
2. `tools.yaml` — Allowed/denied tool permissions (glob support)
3. `routing.yaml` — Optional model routing overrides
4. `memory_init.json` — Initial memory context
5. `voice_ref.txt` — TTS voice reference text

Optional: `voice_ref.wav`, `wake.onnx`. Template at `personas/_template/`.

---

## Data Flows

### Voice Interaction

```
User speech → Pi Microphone → STT (Pipecat) → transcript
  → orchestrator/graph.py: draft_node (LLM via litellm)
  → critic_node (security guard + persona check)
  → respond_node (finalize/suppress)
  → TTS → Pi Speaker → User hears response
  → memory/store.py: episode_add() (L2 write)
```

### Memory Consolidation

```
DreamWorker (periodic: idle 30min / 3AM cron / >20 pending)
  → episode_list_recent() (read L2)
  → LLM extraction (cheap model, 5 categories)
  → quality gate (≥0.7)
  → dream_add() (L3 write)
  → prune_old_episodes() (cleanup)
```

### Evaluation

```
YAML test case → harness → agent_func (optional) → JudgeEnsemble
  → 5 judges score independently (parallel)
  → debate round (optional)
  → weighted aggregation → verdict (pass/fail/uncertain)
  → Calibrator (periodic): gold probes → weight update → feedback to ensemble
```

---

## Configuration

### config.yaml (root)
- Memory: SQLite, L1 12K budget, FTS5, DreamWorker at 3AM, quality 0.7
- Router: >200 chars or smart keywords → smart model
- Breaker: max 15 steps
- Tracer: 90-day retention, dashboard `127.0.0.1:8080`
- Rate limits: Bilibili 3/day, NCM 200/day
- Security: jury consensus 0.75

### backend/litellm/router.yaml
- 7 model slots via aihubmix.com / build.nvidia.com
- Per-role token limits (main: 8K/2K, cheap: 4K/1K, judge: 6K/1K)
- Judge models at temp 0.2

### backend/secrets/llm_keys.env
- Required: `AIHUBMIX_API_KEY`, `NVIDIA_API_KEY`
- Optional: `DASHSCOPE_API_KEY` (TTS), `BOCHA_API_KEY` (search), CalDAV creds, Postgres

---

## Deployment

- **Docker Compose** (`deploy/docker-compose.yml`): 6 services — backend, Bilibili MCP, NCM MCP, search MCP, optional CosyVoice TTS, optional PostgreSQL
- **Edge** (`deploy/systemd/edge-runtime.service`): systemd unit for Pi
- **VPN** (`deploy/wireguard/setup.sh`): WireGuard tunnel setup script
- **Hardware check** (`deploy/check_hardware.sh`): Pi diagnostics
