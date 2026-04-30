# 实施计划

> 对应设计文档：`plan.md`
> 当前状态：P0 完成（185 smoke 测试通过，LLM tool calling 端到端验证）

---

## 总览

| 阶段 | 目标 | 关键交付 | 预计周期 |
|------|------|---------|---------|
| P1 | 去 Pi，单机运行 | HAL 简化，WireGuard 删除，edge/ 本机化 | 1 周 |
| P2 | 人格系统重构 | 名字唤醒，L2 独立记忆，voice_ref TTS | 1 周 |
| P3 | 流式语音管道 | STT/LLM/TTS 三路并行，延迟 ≤ 500ms | 2 周 |
| P4 | 主动感知 | 定时扫描器，情绪感知，人脸触发问候 | 1 周 |
| P5 | 社区人格包 | `.persona` 格式，CLI install/export | 1 周 |
| P6 | 开源发布 | README，CONTRIBUTING，完整评测报告 | 1 週 |

---

## P1：去 Pi，单机运行

**目标**：删除跨机通信层，edge/ 模块直接在游戏本本机运行，smoke 测试全部保持绿色。

### 删除

| 文件/目录 | 原因 |
|----------|------|
| `deploy/wireguard/` | WireGuard 配置不再需要 |
| `core/hal.py` 中 `RPiHAL`、`RemoteHAL` 实现 | 只保留 `LocalHAL` 和 `MockHAL` |
| `deploy/docker-compose.yml` 中 edge 服务的远程挂载配置 | 改为本机直接挂载 |

### 修改

| 文件 | 改动 |
|------|------|
| `core/hal.py` | 删除 RPiHAL / RemoteHAL，LocalHAL 成为默认实现 |
| `core/router.py` | 移除远程 edge endpoint 路由逻辑 |
| `deploy/docker-compose.yml` | 合并为单机服务，去掉跨机网络配置 |
| `CLAUDE.md` | 更新架构描述 |

### 验收

```bash
python -m pytest tests/smoke_test.py -v   # 185 项全绿
python main.py --persona assistant        # 本机正常启动
```

---

## P2：人格系统重构

**目标**：每个人格有独立名字作为唤醒词，独立 L2 记忆，独立 voice_ref 驱动 TTS 音色。

### 新增

| 文件 | 内容 |
|------|------|
| `personas/xiaolin/persona.yaml` | 示例人格：晓林 |
| `personas/xiaolin/system.jinja2` | 晓林的 system prompt 模板 |
| `personas/xiaolin/voices/ref.wav` | 晓林的声音参考（3-10s） |
| `personas/_template/persona.yaml` | 新建人格时的起点模板 |

### 修改

| 文件 | 改动 |
|------|------|
| `core/persona.py` | 添加 `wake_word: str`、`voice_ref: str` 字段 |
| `core/types.py` | `AgentState` 添加 `active_persona_id: str` |
| `edge/wakeword.py` | 启动时从所有 persona.yaml 加载 wake_word 列表，动态注册唤醒词 |
| `backend/memory/store.py` | L2 表名改为 `episodic_{persona_id}`；L3 保持全局 `semantic` 表；读取时按 persona_id 过滤 |
| `backend/memory/dream.py` | `nightly_dream` 遍历所有 persona_id，各自读 L2，合并写 L3 |
| `backend/orchestrator/graph.py` | 收到唤醒事件时，按 persona_id 加载人格配置 + 对应 L2 记忆 |
| `backend/tts/cosyvoice_client.py` | 接受 `voice_ref` 参数，零样本克隆合成 |

### 记忆路由规则（写入 `backend/memory/router.py`，新建）

```python
SHARED_KEYWORDS = ["情绪", "事件", "偏好", "习惯", "决定"]

def route(content: str, current_persona_id: str) -> Literal["L2", "L3"]:
    # 包含共性关键词 → L3 共享
    # 否则 → L2 当前人格独立
```

### 验收

```bash
# 叫晓林的名字触发，加载晓林人格和她的 L2
python main.py
# > 晓林，今天怎么样？
# 期望：晓林的声音回答，记忆写入 episodic_xiaolin 表

# 叫另一个人格，确认拿不到晓林的 L2
# 期望：assistant 不知道刚才和晓林说了什么

python -m pytest tests/smoke_test.py -k "memory or persona" -v
```

---

## P3：流式语音管道

**目标**：STT/LLM/TTS 三路流水线并行，端到端首字节延迟 ≤ 500ms。

### 新增

| 文件 | 内容 |
|------|------|
| `backend/streaming/pipeline.py` | 协调三路 stream 的异步管道 |
| `edge/emotion.py` | 声学特征提取，输出 `EmotionContext` |

### `backend/streaming/pipeline.py` 核心逻辑

```python
async def run_pipeline(audio_stream, persona_id: str) -> None:
    # 1. STT stream → token queue
    # 2. 首 token 到达 → 启动 LLM stream（无需等 STT 完成）
    # 3. LLM 首 token → 启动 TTS stream
    # 4. TTS 音频块 → 实时送音箱
    # 全程 asyncio.gather，三路并行
```

### 修改

| 文件 | 改动 |
|------|------|
| `edge/audio_routing.py` | 改为 yield 音频块的异步生成器 |
| `backend/tts/cosyvoice_client.py` | 支持 streaming 输出（yield 音频块） |
| `backend/litellm/client.py` | 确保 `stream=True`，yield token |
| `backend/orchestrator/graph.py` | 接入 pipeline，LangGraph 节点改为流式 |
| `core/types.py` | 添加 `EmotionContext` dataclass |

### 延迟验收指标

| 阶段 | 目标 | 测量方式 |
|------|------|---------|
| 唤醒词检测 | < 100ms | openWakeWord 内置计时 |
| STT 首词 | < 200ms | pipeline 打点 |
| LLM 首 token | < 300ms | litellm stream 回调 |
| TTS 首音频块 | < 200ms | cosyvoice 回调 |
| **端到端** | **< 500ms** | tracer span |

```bash
python -m pytest tests/smoke_test.py -k "streaming or latency" -v
# 手动测试：说话后 0.5s 内听到回应
```

---

## P4：主动感知

**目标**：agent 能主动触发，而不只是被动回答。

### 新增

| 文件 | 内容 |
|------|------|
| `backend/proactive/scanner.py` | 定时扫描，生成 `ProactiveEvent` 列表 |
| `backend/proactive/triggers.py` | 各类触发条件的判断逻辑 |
| `core/types.py`（追加） | `ProactiveEvent` dataclass |

### `scanner.py` 触发条件

```python
async def proactive_scan(store: MemoryStore) -> list[ProactiveEvent]:
    events = []
    # 1. 明天有日历事件 → 今晚提醒
    # 2. L3 中连续 N 天情绪负面 → 某朋友主动问候
    # 3. 某话题距上次提及超 3 天 → 主动跟进
    # 4. 人脸识别触发「到家」事件 → 播放问候 + 当日摘要
    return events
```

### 修改

| 文件 | 改动 |
|------|------|
| `backend/memory/store.py` | 新增 `query_emotion_trend(days=N)` 查 L3 情绪趋势 |
| `deploy/docker-compose.yml` | 新增 `proactive` 服务，每 5 分钟运行一次 scanner |
| `edge/face_gate.py` | 识别成功时向 proactive 模块发「到家」事件 |

### 验收

```bash
# 手动触发 scanner，确认生成正确事件
python -c "import asyncio; from backend.proactive.scanner import proactive_scan; ..."

python -m pytest tests/smoke_test.py -k "proactive" -v
```

---

## P5：社区人格包

**目标**：人格可以打包、分享、安装，格式标准化。

### 新增

| 文件 | 内容 |
|------|------|
| `tools/persona_pack.py` | pack / unpack / validate `.persona` 文件 |

### `.persona` 包格式（zip）

```
xiaolin.persona
├── persona.yaml          # 人格定义
├── system.jinja2         # system prompt 模板
├── voices/ref.wav        # 声音参考（可选）
├── examples/             # 示例对话（可选，用于评测）
└── README.md             # 人格说明
```

### CLI 命令

```bash
python tools/persona_pack.py pack personas/xiaolin    # → xiaolin.persona
python tools/persona_pack.py install xiaolin.persona  # → 解压到 personas/
python tools/persona_pack.py validate xiaolin.persona # → 检查格式合规
python tools/persona_pack.py export xiaolin           # 同 pack
```

### 验收

```bash
python tools/persona_pack.py pack personas/xiaolin
python tools/persona_pack.py validate xiaolin.persona
python tools/persona_pack.py install xiaolin.persona --target /tmp/test_personas/
# 确认解压结构正确
```

---

## P6：开源发布

**目标**：项目可以被陌生开发者克隆后 30 分钟内跑起来，评测报告公开。

### 新增 / 修改

| 文件 | 内容 |
|------|------|
| `README.md` | 项目介绍、快速开始、架构图、人格系统说明 |
| `CONTRIBUTING.md` | 如何贡献工具、人格包、bug 修复 |
| `docs/persona-guide.md` | 人格创作指南（写 system prompt、录 voice ref） |
| `eval/report.md` | 完整评测结果（9 维指标，覆盖所有阶段） |
| `CLAUDE.md` | 更新架构图、模块说明、会话规则 |

### 开源发布检查清单

- [ ] `python -m pytest tests/smoke_test.py -v` 全绿
- [ ] `docker compose -f deploy/docker-compose.yml up -d` 一键启动
- [ ] README 中 Quick Start 5 步以内可运行 CLI 模式
- [ ] 无硬编码 API key，密钥通过 `.env` 注入
- [ ] 至少 2 个示例人格（含 voice ref 和 system prompt）
- [ ] eval 报告覆盖 9 个维度
- [ ] LICENSE 文件（建议 Apache 2.0）

---

## 贯穿各阶段的原则

- **每个阶段结束，smoke 测试必须全绿**，不允许带着红测试进入下一阶段
- **不改接口只改实现**：现有 smoke 测试是安全网，重构时让它们保持通过
- **新功能先写测试**：proactive、streaming 等新模块在 `tests/smoke_test.py` 中对应新增测试类
- **记忆结构变更谨慎**：L2 表名加 persona_id 前缀是 breaking change，需要迁移脚本

---

*日期：2026-04-29*
