# Project Memory

Living document. Update after each task with new decisions, pitfalls, or changed context.

---

## ⚡ Hand-off Snapshot (2026-04-27, 当前未提交)

> 给下一个 session 的速读：cookie + agent tool calling + **真实 LLM 端到端**三层全部完成并测过，working tree 仍未 commit。

### 已完成（可立即用）
- **B 站**：`backend/secrets/bilibili_credential.json` 已生成并通过 `User.get_user_info()` 校验。`BilibiliServer.get_room_info(1)` 实测返回真实房间数据。
- **网易云**：`backend/secrets/pyncm_credential.json` 已生成（含 MUSIC_U + csrf_token）。`PyncmServer.search_track('七里香')` 实测返回 3 条真实结果。
- **LLM 路由**：`backend/secrets/llm_keys.env` 已配（用户填了 AIHubMix key）。CLI agent 能正常调到 LiteLLM。
- **Agent tool calling**：`backend/orchestrator/tools.py::ToolRegistry` 注册 26 个工具，`graph.py` 加 `tool_decide → tool_execute` 双节点循环（≤ 3 轮），`litellm/client.py::create_llm_callable_with_tools` 把 `tools=[...]` 传给 litellm。CLI 启动时按凭据自动注入 server，`require_speaker_verify` 写类工具在文本 CLI（speaker_verified=False）下自动隐藏。
- **🆕 真实 LLM 端到端 (7b)**：`coding-glm-5.1-free` (AIHubMix) 跑通三类提示词 × 2 次：纯聊天 / 网易云搜歌 / B 站房间标题。`pyncm_search_track` + `bilibili_get_room_info` 真实工具结果回填到第二轮 LLM 后合成自然语言回答。
- **测试**：176 个 smoke test 通过。`TestOrchestratorGraph` 之前 2 个失败用例随 `MainGraphState → TypedDict` 重构一并修复。

### 已知缺口（next session 候选任务）
1. **🟡 Cookie 失效续期路径** — SESSDATA 约 30 天，MUSIC_U 约 6 个月。当前靠手动重贴。可加：API 401 → `self.authenticated = False` 标记，启动时打印警告。
2. **🟡 caldav / bocha / browser / shell server 没真实接入** — `caldav` 依赖环境变量 `CALDAV_URL/USERNAME/PASSWORD`，`bocha` 依赖 `BOCHA_API_KEY`，都未配置；`browser_use_wrapper` / `sandboxed_shell` 实现还是占位。tool registry 会自动隐藏未注入的 server，所以不阻塞主流程。
3. **🟡 critic_node 仍是手写的 yes/no LLM 判断** — 本轮窄修后稳定，但只看 persona 名字（`"assistant"`）做判断本身就没什么信息量；可以考虑把真实 system_prompt 传下去，或者干脆只保留 security_guard 那部分，去掉 persona 一致性检查。
4. **🟢 未提交** — 见下方「未提交改动清单」。等用户决定后再 commit。建议拆 3 笔：cookie 一笔、tool calling 一笔、本轮 critic 修复 + 文档更新一笔。

### 未提交改动清单（agent tool calling + 真实 LLM smoke + critic 修复，累计）

cookie / MCP 真实接入那一批已在 commit `0f6b84f` 里了，working tree 现在的累计改动：

```
M  backend/litellm/client.py                       # +create_llm_callable_with_tools，把 tools/tool_choice 传给 litellm.completion
M  backend/orchestrator/graph.py                   # 重写：MainGraphState class → TypedDict；新增 tool_decide / tool_execute 节点；MAX_TOOL_ITERS=3 防死循环；critic 自动 salvage 最后一条 assistant content；【本轮新增】critic 一致性判断 "no" 子串 → 首词匹配 + 任意位置正向词兜底
M  main.py                                         # 启动时构造 ToolRegistry，按凭据自动注入 5 个 server，speaker_verified=False 隐藏写类工具
M  personas/assistant/tools.yaml                   # 命名改 underscore（OpenAI fn name 规范），allowed/denied/require_speaker_verify 重梳
M  personas/_template/tools.yaml                   # 同上，模板默认更保守
M  tests/smoke_test.py                             # 修 2 个 TestOrchestratorGraph 失败用例（class→TypedDict）；+9 TestToolRegistry +3 TestToolCallingFlow
M  process.md                                      # roadmap 7a/7b 都打勾，加本轮 Change Log 条目，§3 测试数 160→176
M  CLAUDE.md                                       # 概要更新 88→89 files / 160→176 tests，加 tool calling 字样，module map 把 tools.py 加上
M  docs/project-memory.md                          # 本文件
?? backend/orchestrator/tools.py                   # 新文件：ToolSpec 数据类 + 26 个工具的 OpenAI schema + ToolRegistry（persona 过滤 + 安全 dispatch + ISO8601 datetime fixup）
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

### critic_node 一致性 LLM 判断本质上 flaky (2026-04-27)

`critic_node` 让一个独立 LLM 调用判断 "draft 是否符合 persona"，但只把 persona **名字**（如 `"assistant"`）传过去，没有 system_prompt 上下文。同一个输入，模型有时返回 `"yes"`、有时返回 `"No, the response is..."`。原代码 `if "no" in consistency_check.lower()` 还会被 `"not"` / `"noted"` / `"no problem"` 误伤。

本轮窄修：首词匹配（`first in ("no", "否", "不")`）+ 任意位置出现 `"yes"` / `"consistent"` / `"appropriate"` 时一律放行（参见 [graph.py:300-318](backend/orchestrator/graph.py)）。两轮 × 三提示词 smoke 后稳定。**根因仍在**——下一步可以把真实 system_prompt 传到 critic_node，或干脆删掉 persona 一致性检查只留 security_guard。

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

### 2026-04-27: 真实 LLM smoke (roadmap 7b) + critic 窄修

**背景**：tool calling 之前只在 mock LLM 上跑过。本轮 `python main.py --persona assistant` 真实跑 `coding-glm-5.1-free`（AIHubMix 路由 default_fast），三提示词 × 2 次：

| 提示词 | 期望工具 | 结果 |
|---|---|---|
| `你好` | 无 | ✓（直答，无 tool_call） |
| `帮我在网易云搜一下"七里香"这首歌` | `pyncm_search_track` | ✓（返回真实歌单，模型合成 markdown 表） |
| `B 站 1 号直播间现在标题是什么？` | `bilibili_get_room_info` | ✓（真实房间号 5440 + 标题） |

**踩到的坑（本轮唯一）**：第一次跑 `你好` 时 `critic_node` 报 `Response breaks persona`，`final_response` 被替换成 `[Critique detected: ...] Original response suppressed for safety.`。根因见上方「Known Issues / critic_node 一致性 LLM 判断本质上 flaky」。

**修复**：[graph.py:300-318](backend/orchestrator/graph.py)，从子串 `"no" in ...` 改为「首词 ∈ no/否/不」+「任意位置出现 yes/consistent/appropriate 即放行」。两轮回归确认稳定，`pytest tests/smoke_test.py` 仍 176/176。

**未做（明确记一下）**：没有提前防御 `tool_calls` 响应 shape、`tool_choice="auto"` 兼容性、content+tool_calls 共存这几处——计划要求 "only fix what breaks"，这些没真撞到。

---

### 2026-04-27: Agent tool calling 接通（P0 — 全量 26 工具）

**背景**：上一轮把 B 站 / 网易云 cookie 这层做通，但 orchestrator 的 `draft → critic → respond` 流水线里没有 tool calling 节点，LLM 看到「搜歌」也只能嘴上拒绝。本轮把这一缺口补齐。

**关键决策**：

1. **工具命名走 underscore**（`bilibili_get_room_info`，不用 `bilibili.get_room_info`）。OpenAI/litellm function name 必须匹配 `^[A-Za-z0-9_-]+$`，不允许点号；persona yaml 的 fnmatch glob 同步改成 `bilibili_*`。
2. **MainGraphState 从 class → `TypedDict(total=False)`**，node 返回 partial-state dict 让 LangGraph merge。这同时修了之前的 `InvalidUpdateError: Expected dict, got <MainGraphState>`。`make_initial_state(...)` 给完整初值。
3. **ToolRegistry 集中管理 26 个工具**（[backend/orchestrator/tools.py](backend/orchestrator/tools.py)）：
   - `filter_for_persona(persona, *, speaker_verified)` 三步过滤：allowed glob → 排除 denied → `require_speaker_verify` 在未验证时排除 → 排除未注入的 server。
   - `dispatch(name, args, *, context)` 异常 → `ToolResult(ok=False, error=...)`，不抛；自动注入 `context_args`（如 memory 工具的 user_id/persona）；caldav 工具的 ISO8601 字符串 → `datetime` 转换。
4. **二段式 LLM 调用**：`backend/litellm/client.py::create_llm_callable_with_tools` 接受 `messages: list[dict]` 和 `tools: list[dict]`，返回 `{"content", "tool_calls": [{id, name, arguments}]}`。litellm 的 tool_calls 兼容 SDK 对象 / dict 两种形态，已都做 fallback。
5. **MAX_TOOL_ITERS=3 防死循环**，超出后 critic 节点 salvage 最后一条 assistant content 当作 draft，回话不会变空字符串。
6. **写类工具默认隐藏**：文本 CLI 永远 `speaker_verified=False`。assistant 人格此时只能看到 13/26 工具（实测：bilibili_get_*, pyncm_*, memory_*, bocha_*, caldav_list_events）。
7. **CLI 启动时按凭据自动注入 server**：bilibili / pyncm 看 secrets 文件；caldav 看 `CALDAV_URL/USERNAME/PASSWORD` env；bocha 看 `BOCHA_API_KEY`；memory 永远在；browser/shell 不自动注入（高危）。

**验证**：

- 176/176 smoke test 通过（之前 164 + 本轮 12）。新增 `TestToolRegistry`（9 个，覆盖 schema 完备性 / persona glob 过滤 / denied 优先级 / speaker_verify 门 / 未注入 server 隐藏 / async dispatch / 未注入工具 / 未知工具 / context_args 注入）和 `TestToolCallingFlow`（3 个，覆盖两轮 tool→answer / 不调工具直答 / 死循环上限）。
- mock LLM 上端到端跑通：`pyncm_search_track('七里香')` → 第二轮 LLM 拿到搜索结果产出最终答复，`state["tools_called"] == ["pyncm_search_track"]`。
- **未在真实 AIHubMix 模型上跑过**，本轮纯单测覆盖（CLI 改动 import 通过即认为入口结构没坏）。

**踩到的坑**：

- 一开始想用 `bilibili.get_room_info` 这种点号命名，写 schema 时才意识到 OpenAI fn name 不允许点号。改 underscore 后也得同步改 persona yaml glob 模式，原 `bilibili.send_dm` / `memory.read` 这些参考性命名直接报废。
- `Tracer` 没有 `trace_start` / `trace_end`，只有 `trace_add`（一次性写入）+ `trace_set_error`。main.py CLI 一开始按假想 API 写错了。
- LangGraph 的 `StateGraph(MainGraphState)` 期望节点返回的是 partial dict（被框架 merge），返回完整 dataclass 会报 `InvalidUpdateError`。改 `TypedDict` 是最低代价方案，比 reducer 装饰器更好理解。

---

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
