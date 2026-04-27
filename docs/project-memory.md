# Project Memory

Living document. Update after each task with new decisions, pitfalls, or changed context.

---

## Important Decisions

### SQLite over Postgres (2026-04-26)
SQLite is the primary persistence layer (WAL mode, FTS5). PostgreSQL is optional and only in Docker Compose as an alternative backend. Rationale: zero-config for dev, single-file portability, sufficient for single-user agent.

### LiteLLM proxy via aihubmix.com
Model calls route through aihubmix.com (China-based direct-connect proxy) and build.nvidia.com. This avoids direct API calls to Western providers that may be blocked/unstable from China. Config in `router.yaml`, factory in `client.py`.

### LangGraph with sequential fallback
Graph uses LangGraph's `StateGraph` when available, silently falling back to sequential dict execution. This ensures the agent loop works even if langgraph is not installed or broken. See `orchestrator/graph.py:build_main_graph()`.

### FTS5 text search over vector search
L2 episodic memory uses SQLite FTS5 for full-text search. `EmbeddingProvider` exists with BGE-M3 support but is **not wired** to the memory store. Vector search is future work.

### 5-judge ensemble for evaluation
Evaluation uses 5 independent LLM judges scoring in parallel, optional debate round, weighted aggregation. Weights are calibrated via gold-standard probes. This design prioritizes reliability over speed/cost.

### Multiplicative calibration updates
Judge weights update multiplicatively: ×1.01 on hit, ×0.97 on miss, clamped [0.5, 1.5]. Gentle enough to avoid overfitting to any single probe, persistent enough to correct systematic bias over time.

---

## Known Issues & Pitfalls

### CircuitBreaker fixed (2026-04-27)
`CircuitBreaker` was missing `is_healthy()` and `trip()` methods that callers expected. Fixed in commit `b2697ce`. Smoke tests now explicitly verify these exist (see `TestCircuitBreakerIntegration` at bottom of `tests/smoke_test.py`).

### TTS/STT are placeholders
The voice pipeline (`backend/tts/*`, STT in `pipecat_app.py`) uses `asyncio.sleep` + dummy bytes. Real TTS/STT integration is not done. Voice eval cases exist but can't run against real audio yet.

### EmbeddingProvider not consumed
`backend/memory/embedding_provider.py` has working embedding with fallback, but `store.py` uses only FTS5 text search. Semantic/vector search is not implemented.

### No CI/CD
No `.github/` directory, no CI workflows. All testing is manual. Docker Compose and systemd units exist for deployment but have no automated pipeline.

### Very early stage
Only 2 git commits (2026-04-26 and 2026-04-27). Initial commit was monolithic — entire project skeleton in one dump. No branching history.

### CalDAV blocking in async context
`caldav.py` uses `ThreadPoolExecutor` for blocking CalDAV calls. If the executor is saturated, calendar operations can stall. Relevant for high-frequency calendar polling scenarios.

### WireGuard setup is manual
`deploy/wireguard/setup.sh` exists but requires manual key generation and configuration on both Pi and backend. No automatic provisioning.

---

## Conventions Not Obvious from Code

### File-level
- Every Python file starts with `from __future__ import annotations`
- No top-level test imports — every test method imports its deps inline to stay self-documenting
- `plan.md` is the design authority — code docstrings reference it (e.g., "Per plan.md §4.2")

### Patterns
- **Pydantic v2 for external boundaries** (Message, AgentState), **dataclasses for internals** (Persona, ToolResult)
- **SQLite WAL mode** everywhere — `PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;`
- **threading.Lock for SQLite** in multi-threaded contexts, **asyncio.Lock for coroutine-level** mutual exclusion
- **Mock LLMs** are sync callables: `lambda system, user_msg, persona=None: "mock response"`
- **DB tests** use `tmp_path` fixture with in-memory or temp-file SQLite

### Naming
- Chinese persona names: `assistant/` = "小安" (Xiao An)
- Commit messages: Chinese `主题：详情` format
- Bilingual codebase: code identifiers are English, comments and docs are mixed Chinese/English

### Security
- External content wrapped in `<external_content source=... trust=untrusted>` XML tags
- Injection detection via 5 regex patterns (not ML-based)
- High-risk tools (shell, browser, bilibili_post) require special handling in guard

---

## Session Log

<!-- 
After each task, append a brief entry:
### YYYY-MM-DD: <task summary>
- Decision: ...
- Pitfall discovered: ...
- Changed: ...
-->

### 2026-04-27: Initial documentation (CLAUDE.md, architecture.md, project-memory.md)
- Created three documentation files to bootstrap Claude Code session context
- Captured architecture, conventions, and known issues from codebase analysis
