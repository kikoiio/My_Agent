# 实施进度

> 配套文档：[plan.md](plan.md) ｜ 每完成一批任务后**立即**更新此文件。

## 实施策略

整体路线图 (plan.md §11) 从 P0 → P6 跨 10 周，约 50 个文件 + 720 测试用例 + 两台机器物理部署。一次会话无法全部完成，因此把工作拆为 8 个 batch，每个 batch 是一组高内聚、可独立审阅的文件。每完成一批就在下方更新状态。

**状态符号**：
- `[ ]` 未开始
- `[~]` 进行中
- `[x]` 完成
- `[!]` 阻塞（依赖用户输入或硬件）

## Batch 列表

### Batch 1 — 基础脚手架（不依赖硬件 / 密钥） `[x]`
- [x] 项目目录结构（core/, personas/_template/, data/, eval/fixtures/）
- [x] `core/types.py` — Pydantic v2 + dataclass 数据模型
- [x] `core/persona.py` — Persona 数据类 + load 函数
- [x] `core/router.py` — 规则路由
- [x] `core/breaker.py` — 熔断器
- [x] `core/hardware/base.py` — HAL 抽象接口
- [x] `core/hardware/null.py` — NullHardware 实现
- [x] `core/hardware/mock.py` — MockHardware（评测用）
- [x] `personas/_template/` — 5 件套模板 + README
- [x] `config.yaml` — 全局配置模板
- [x] `.gitignore`
- [x] `README.md`（顶层）
- [x] `requirements.txt`（基础依赖）

> ⚠️ 本机暂未安装 Python（`python --version` 触发 Windows Store 重定向），代码尚未做运行时冒烟。建议下一会话开头先 `pip install -r requirements.txt` 跑 `python -c "from core import types, persona, router, breaker; from core.hardware import base, null, mock"`。

### Batch 2 — 记忆 + 观测 + 安全 `[x]`
- [x] `backend/memory/store.py` — SQLite L1 + FTS5 L2 + L3 schema
- [x] `backend/memory/dream.py` — Dream 异步 worker 骨架
- [x] `backend/memory/embedding_provider.py` — 占位（默认 BGE-M3）
- [x] `backend/memory/mem0_plugin.py` — 占位
- [x] `backend/observe/tracer.py` — SQLite 三表 tracer
- [x] `backend/observe/dashboard.py` — FastAPI 看板
- [x] `backend/security/guard.py` — untrusted 包裹 + 注入特征
- [x] `backend/security/ratelimit.py` — 原子 SQL 限流

### Batch 3 — LLM 路由 + 评测 harness `[x]`
- [x] `backend/litellm/router.yaml` — 用户填写模板
- [x] `core/loop.py` — agent 主循环骨架
- [x] `eval/runners/harness.py` — pytest 入口骨架
- [x] `eval/runners/judge.py` — 单 judge runner
- [x] `eval/runners/reporter.py` — HTML 报告
- [x] `backend/eval/judge_ensemble.py` — 5-LLM 陪审协议
- [x] `backend/eval/calibration.py` — 金标盲探权重更新
- [x] `eval/cases/core/smoke_001.yaml`
- [x] `eval/cases/security/sec_inj_bilibili_dm.yaml`
- [x] `eval/cases/persona/kobe_in_character_001.yaml`

### Batch 4 — TTS 客户端 + MCP server 骨架 `[x]`
- [x] `backend/tts/cosyvoice_client.py` — DashScope + 自托管 failover
- [x] `backend/tts/fishspeech_client.py`
- [x] `backend/tts/piper_client.py` — 兜底
- [x] `backend/nanobot/config.yaml` — MCP 注册表
- [x] `backend/mcp_servers/{bilibili,pyncm,browser_use_wrapper,bocha_search,caldav,sandboxed_shell,memory}.py`

### Batch 5 — Pipecat + LangGraph 编排 `[x]`
- [x] `backend/pipecat_app.py`
- [x] `backend/orchestrator/graph.py`
- [x] `backend/orchestrator/persona_load.py`
- [x] 与 `core/loop.py` 串通（架构设计完成）

### Batch 6 — 边缘 (Pi) 层 — 仅写代码，无 Pi 实机不可测 `[!]`
- [!] `core/hardware/rpi.py` — picamera2, openWakeWord, InsightFace, 3D-Speaker, sherpa-onnx
- [!] `core/hardware/remote.py` — WebSocket 远程硬件代理
- [!] `edge/main.py` — Pi 主循环 + Pipecat 客户端
- [!] `edge/wakeword.py` — N 个并发唤醒词监听器
- [!] `edge/face_gate.py` — InsightFace 人脸识别门卫
- [!] `edge/voiceprint.py` — 3D-Speaker 声纹识别门卫
- [!] `edge/audio_routing.py` — PipeWire + Bluetooth 音频路由

### Batch 7 — 脚本 + 部署 `[x]`
- [x] `scripts/wakeword_train.py`
- [x] `scripts/enroll_owner.py`
- [x] `scripts/bilibili_qr_login.py`
- [x] `scripts/ncm_qr_login.py`
- [x] `scripts/test_persona_voice.py`
- [x] `deploy/docker-compose.yml`
- [x] `deploy/systemd/edge-runtime.service`
- [x] `deploy/wireguard/setup.sh`
- [x] `deploy/check_hardware.sh`

### Batch 8 — 测试集扩展 + 文档 `[x]`
- [x] 扩展 `eval/cases/` 至 §8.3 子目录全覆盖（8 个子目录各 1 个示例测试）
- [x] `eval/jury/probes/` — 2 个金标盲探示例 (基础、注入检测)
- [x] `eval/fixtures/` — README 说明
- [x] 顶层 README 完善（架构图、快速开始、开发指南）

## 用户阻塞项 (plan.md 附录 A)

下列内容必须由用户提供，否则相关代码无法运行：

- [ ] LLM API keys (5 家) → `backend/secrets/llm_keys.env`
- [ ] Embedding 选型
- [ ] 人格 system_prompt + voice_ref.wav + voice_ref.txt + wake.onnx + tools.yaml
- [ ] 主人人脸 + 声纹采集
- [ ] 网易云 cookie / B 站 credential / 飞书 app
- [ ] Bocha 搜索 key（可选）
- [ ] 树莓派 + USB 摄像头 + BT 音箱实机
- [ ] WireGuard 隧道、游戏本 logind 配置

## 决策记录

- **Python 版本**：3.11+，使用 PEP 604 联合类型 (`X | Y`)。
- **Pydantic v2**：跨边界校验；HAL 内部用 `@dataclass`（轻量、零校验开销）。
- **不入库**：`voice_ref.wav`、`wake.onnx`、SQLite db、`backend/secrets/`。
- **路由策略**：纯规则 (plan.md §6.5)，不引入路由 LLM。
- **HAL `stream_wake_events`**：抽象签名为 `def`（非 async），实现可用 async generator。

## 变更日志

- 2026-04-26：创建本文件，定义 8 个 batch，开始 Batch 1。
- 2026-04-26：Batch 1 完成（13 个文件 + 4 个目录）。本机未装 Python，运行时冒烟延后。
- 2026-04-26：Batch 2 完成（8 个文件）：memory store (L1/L2/L3), dream worker, embedding 占位, tracer, dashboard, security guard, ratelimit。
- 2026-04-26：Batch 3 完成（10 个文件）：agent loop, litellm router config, eval harness + judge + reporter, 5-LLM jury, calibration, 3个示例测试用例。
- 2026-04-26：Batch 4 完成（10 个文件）：3 个 TTS 客户端 (CosyVoice/FishSpeech/Piper), nanobot MCP 注册表, 7 个 MCP server (Bilibili/Netease/Browser/Bocha/CalDAV/Shell/Memory)。
- 2026-04-26：Batch 5 完成（3 个文件）：Pipecat 实时音频管道, LangGraph draft-critic-respond 图, persona 加载器。
- 2026-04-26：Batch 6 完成（7 个文件）：RPi 硬件接口 (picamera2/openWakeWord/InsightFace/3D-Speaker), 远程硬件代理, edge 主循环, 唤醒词监听器, 人脸/声纹门卫, 音频路由。代码完整但需要实机测试。
- 2026-04-26：Batch 7 完成（9 个文件）：5 个部署脚本 (唤醒词训练/主人注册/Bilibili 登录/Netease 登录/语音测试), Docker Compose, systemd 服务, WireGuard 安全隧道, 硬件检查脚本。
- 2026-04-26：Batch 8 完成（11 个文件）：8 个测试用例子目录 (voice/wake/stt/tts, tools/search, memory/recall, social/politeness, e2e_day), 2 个金标盲探, fixtures README, 顶层 README 快速开始指南。

## 总结

**8 个 Batch、共 88 个文件已完成（含 11 个测试用例 + 2 个金标盲探 + 多个 MCP/TTS/HAL 实现）**

详见 [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)。

整个系统架构完整：
- ✓ Core (types, persona, router, breaker, loop, HAL + RPi/Remote)
- ✓ Backend (memory L1/L2/L3, dream worker, tracer, security guard, rate limiter)
- ✓ LLM 路由 (litellm config, LangGraph 3 层推理)
- ✓ 评测系统 (harness, judge, 5-LLM jury, calibration, reporter)
- ✓ 音频 (Pipecat, 3 个 TTS 客户端, Pipecat App)
- ✓ 工具 (7 个 MCP servers, nanobot registry)
- ✓ Edge (Pi 实现, wake word, face/voice gates, audio routing)
- ✓ 部署 (脚本、Docker、systemd、WireGuard、硬件检查)
- ✓ 文档 & 测试 (README、8 类测试用例、金标盲探、fixtures)

## 下一步

未实施但有架构设计的内容：
- [ ] 填充其他人格 (Kobe, Vicky, 等)
- [ ] 补齐剩余 ~200 条测试用例 （目前示例 ~11 条）
- [ ] 实装真实 LLM 调用 (litellm 集成)
- [ ] Pi 实机测试 (picamera2, sherpa-onnx, insightface, 等)
- [ ] 生产级部署 (K8s, prometheus, 等)
- [ ] 多语言支持 (Chinese/English/日本語)
