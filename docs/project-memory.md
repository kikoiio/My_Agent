# Project Memory

Living document. Update after each task with new decisions, pitfalls, or changed context.

---

## ⚡ Hand-off Snapshot (2026-04-27, 当前未提交)

> 给下一个 session 的速读：cookie/凭据这一层全部完成并端到端验证通过，但所有改动 **还在 working tree，未 commit**。Agent 还不能真正调用 MCP 工具（这是下一笔活）。

### 已完成（可立即用）
- **B 站**：`backend/secrets/bilibili_credential.json` 已生成并通过 `User.get_user_info()` 校验。`BilibiliServer.get_room_info(1)` 实测返回真实房间数据。
- **网易云**：`backend/secrets/pyncm_credential.json` 已生成（含 MUSIC_U + csrf_token）。`PyncmServer.search_track('七里香')` 实测返回 3 条真实结果。
- **LLM 路由**：`backend/secrets/llm_keys.env` 已配（用户填了 AIHubMix key）。CLI agent 能正常调到 LiteLLM。
- **测试**：164 个 smoke test 通过（含本次新增 4 个 MCP server 测试）。

### 已知缺口（next session 候选任务）
1. **🔴 Agent 无法调用 MCP 工具** — `backend/orchestrator/graph.py` 的 draft→critic→respond 流程没有 tool calling 节点。LLM 即使收到「搜歌」也只会嘴上拒绝。**这是当前最大的功能缺口**。
   - 要做：给 `BilibiliServer` / `PyncmServer` 的方法生成 LiteLLM tool schema → orchestrator 加 tool-calling 节点（draft → tool_call? → execute → respond）→ ToolResult 注入上下文二次生成
   - 估计工作量：本次 cookie 任务的 2-3 倍
   - 入口文件：[backend/orchestrator/graph.py](backend/orchestrator/graph.py)、[backend/litellm/client.py](backend/litellm/client.py)
2. **🟡 TestOrchestratorGraph 2 个测试失败** — `test_build_main_graph`、`test_run_graph` 在当前 LangGraph 版本下报 `InvalidUpdateError: Expected dict, got <MainGraphState>`。**与本次工作无关**（stash 后仍复现），但应单独修。`MainGraphState` 是 dataclass，LangGraph 期望 dict 返回值。
3. **🟡 Cookie 失效续期路径** — SESSDATA 约 30 天，MUSIC_U 约 6 个月。当前靠手动重贴。可加：API 401 → `self.authenticated = False` 标记，启动时打印警告。
4. **🟢 未提交** — 见下方「未提交改动清单」。等用户决定后再 commit。

### 未提交改动清单

```
M  .gitignore                                      # 加 !backend/secrets/*.env.example 例外
M  backend/mcp_servers/bilibili.py                 # 占位 → 真实接入 bilibili-api-python v17，加 _register_http_client
M  backend/mcp_servers/pyncm.py                    # 占位 → 真实接入 pyncm 1.8，用 Session().load(dict)
M  docs/project-memory.md                          # 本文件
M  requirements.txt                                # 取消注释 bilibili-api-python/pyncm，加 browser-cookie3，删 qrcode/browser-use
M  tests/smoke_test.py                             # +4 个 MCP server 测试（TestBilibiliServer/TestPyncmServer）
RM scripts/bilibili_qr_login.py → scripts/bilibili_cookie_import.py   # 整体重写
?? backend/secrets/accounts.env.example            # 第三方账号凭据模板（B 站 4 cookie + NCM MUSIC_U）
?? backend/secrets/llm_keys.env.example            # LLM API key 模板（项目原本缺）
?? scripts/pyncm_login.py                          # 网易云登录脚本，方法 A=MUSIC_U cookie, 方法 B=phone+password
?? scripts/verify_mcp_servers.py                   # 端到端验证脚本：直连 server，跳过 LLM
```

实际本机 secrets（**不入 git**）：`backend/secrets/{accounts.env, llm_keys.env, bilibili_credential.json, pyncm_credential.json}` 都已在本地填好。

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

### bilibili-api-python v17+ 必须显式注册 HTTP 客户端 (2026-04-27)
v17 把 HTTP 客户端做成可插拔。任何 API 调用前必须先选一个 impl，否则报 `ArgsException('尚未安装第三方请求库或未注册自定义第三方请求库')`。`BilibiliServer.__init__` 已在加载 credential 后调 `_register_http_client()`，按 `aiohttp/httpx/curl_cffi` 顺序尝试 `select_client()` 或 `request_settings.set_impl()`。aiohttp 是项目已有依赖。

### 网易云账密登录被风控 (2026-04-27)
`pyncm.LoginViaCellphone(phone, password)` 几乎必中 `code 8821 需要行为验证码验证`，跳转到 `qa-yyy.igame.163.com/anquanhuanjingfengxian`。**账密路径基本不可用**，必须走 MUSIC_U cookie 手动导入。`scripts/pyncm_login.py` 默认走方法 A（MUSIC_U），方法 B（账密）保留作 fallback。

### Edge/Chrome 2024+ App-Bound Encryption 阻断 cookie 自动读取 (2026-04-27)
Chromium 自 2024 年起对 cookie 数据库加了 App-Bound Encryption，`browser-cookie3` 解不开，报 `Unable to get key for cookie decryption`。Firefox 不受影响。`scripts/bilibili_cookie_import.py` 因此默认走方法 A（DevTools 手动复制 4 个 cookie 到 env），方法 B（browser-cookie3）保留作 fallback、默认浏览器调成 firefox。

### pyncm 1.8 有两套互不兼容的序列化 (2026-04-27)
- `Session.dump() → dict` / `Session.load(dict)`：人类可读，4 字段（`eapi_config / login_info / csrf_token / cookies`）
- `DumpSessionAsString() → str` / `LoadSessionFromString(str)`：`"PYNCM" + base64(zlib(json(dump())))`，二进制不可读

**两套不能混用**。`LoadSessionFromString` 看到非 `PYNCM` 前缀会走 `parse_legacy`，把 JSON 当 hex 解析，报 `invalid literal for int() with base 16: '{"'`。我们用前者（JSON 可读，便于排查）。`PyncmServer._load_session` 用 `Session().load(dict)`。

### 网易云 EAPI 签名缺 __csrf 时解码崩溃 (2026-04-27)
若只填 MUSIC_U 不填 `__csrf`，调 EAPI 类接口（如 `GetCurrentLoginStatus`）时服务器返回 JSON 错误页，pyncm 仍按 hex 加密响应解析，崩 `int(x, 16)`。读类接口（搜歌、查歌单）走 weapi，只要 MUSIC_U 就够。建议两个 cookie 都填。

### Windows cmd.exe GBK 编码导致中文输出乱码 (2026-04-27)
`scripts/verify_mcp_servers.py` 在 cmd 里输出中文歌名/房间名是乱码，但数据本身是 UTF-8 完好。换 PowerShell 或 Windows Terminal 即正常显示。不修。

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

### 2026-04-27: B 站 / 网易云 cookie 登录方案落地（多轮迭代后定稿）

**最终方案**（详见上方「Hand-off Snapshot」与「Known Issues」新增条目）：
- **B 站**：方法 A（推荐）从 DevTools 手动复制 4 个 cookie（`SESSDATA / bili_jct / buvid3 / DedeUserID`）到 `accounts.env`；方法 B 用 browser-cookie3 自动读浏览器（Firefox 可用，Edge/Chrome 受 App-Bound Encryption 阻断）。
- **网易云**：方法 A（推荐）从 DevTools 复制 `MUSIC_U` + `__csrf` cookie；方法 B 走 `LoginViaCellphone` 账密登录（被 8821 风控，几乎不可用）。
- **MCP server 真实接入**：`BilibiliServer` 用 bilibili-api-python v17 的 `LiveRoom.get_room_info/send_danmaku/get_chat_msg`；`PyncmServer` 用 pyncm 1.8 的 `cloudsearch.GetSearchResult / playlist.GetPlaylistInfo / user.GetUserPlaylists`。所有调用 try/except 降级，不阻塞 LLM 主流程。
- **配置布局**：`backend/secrets/accounts.env`（第三方账号）+ `backend/secrets/llm_keys.env`（LLM key），都有 `.example` 模板入 git，实际值 `.gitignore` 屏蔽。`.gitignore` 加 `!backend/secrets/*.env.example` 例外允许模板入库。

**端到端验证脚本** `scripts/verify_mcp_servers.py` 实测：
- B 站 `get_room_info(1)` → `room_id=5440, title='再燃一次吧！男V女V向前冲【正在直播】', live_status=2`（真实直播间）
- 网易云 `search_track('七里香')` → 3 条真实结果

**踩过的坑（按发现顺序）**：
1. bilibili-api-python v17 不自带 HTTP 客户端，要 `select_client('aiohttp')` 显式注册（已加 `_register_http_client`）
2. Edge/Chrome 2024+ App-Bound Encryption 阻断 browser-cookie3
3. 网易云账密登录被 code 8821 行为验证码风控
4. pyncm Session.dump()/.load() 与 DumpSessionAsString/LoadSessionFromString 是两套不兼容的序列化（前者裸 dict 可读，后者 PYNCM-base64-zlib），混用会被 `parse_legacy` 当 hex 解析崩溃
5. pyncm `Session.dump()` 包含 `cookies` 字段（list of dict），不是直接序列化 requests jar；setter 把它们 `.set(**cookie)` 回 jar
6. pyncm 校验 EAPI 接口（`GetCurrentLoginStatus`）需要 `__csrf` cookie，否则签名失败、解码 JSON 错误页时崩 `int(x, 16)`
7. pyncm `LoginViaCellphone` 内部自动 md5 password — 必须传明文
8. bilibili `LiveDanmaku` 是事件流不是历史拉取；要快照用 `LiveRoom.get_chat_msg(number=N)`
9. 项目原本缺 `llm_keys.env.example`，CLAUDE.md 提了但没建文件；本次顺手补上

**测试**：4 个新 smoke test 用 monkeypatch 桩 `bilibili_api` / `pyncm` 模块，不依赖真实库装机。164/164 通过。`TestOrchestratorGraph` 的 2 个失败与本次工作无关，是 LangGraph + dataclass `MainGraphState` 的预存在问题。
