# 多人格本地语音 AI Agent —— 设计文档

> 开源、可自托管、基于现代 Agent 技术的本地语音伴侣平台。

---

## §0 最终愿景

### 这是什么

一个运行在你自己电脑上的语音 AI 伴侣平台。你可以拥有多个「朋友」——每个都有独立的名字、声音、性格和与你的关系史。你叫他们的名字，他们回应，他们记得你说过的话，他们越来越懂你。

这不是 Alexa 的替代品，是 Alexa 没有做到的事：**有记忆、有人格、在本地、开源**。

### 和它生活在一起是什么感觉

> 你下班到家，摄像头认出你。音箱响起来：「回来了，今天四个会，要来点什么？」
>
> 你说：「随便放点。」
>
> 它知道你说随便的时候通常不太好，放了你上周循环最多的那首歌，没多说话。
>
> 过了一会儿你叫了另一个朋友的名字，聊了半小时工作上的烦恼。它记住了，但不会告诉其他朋友。
>
> 睡前它说：「明天九点有个会，你上次早起忘了吃早饭，要不要提前半小时叫你？」

一个月后，它知道你。六个月后，有点像朋友。

### 对开发者和开源社区

- 完整的企业级架构：LangGraph 编排、3 级记忆、MCP 工具、5-LLM 评测、OpenTelemetry 可观测
- 人格包（`.persona`）格式：社区可创作、分享、下载人格——下载的不是皮肤，是一段潜在的关系
- MCP 工具生态：任何人都可以给它增加新能力
- 一台普通电脑即可运行，无需专用硬件

---

## §1 设计原则

| 原则 | 说明 |
|------|------|
| **本地优先** | 语音不出门，隐私由你掌控；云 API 可选，非必须 |
| **单机运行** | 游戏本即全栈，无需第二台设备或 VPN |
| **人格即朋友** | 每个 Persona 是独立人格，有声音/性格/关系史，不是功能模式 |
| **记忆是核心** | 越用越懂你，这是区别于 Alexa 的最大竞争力 |
| **开源可扩展** | MCP 工具、人格包均可由社区贡献和分享 |
| **企业级可观测** | 完整 tracing / eval / dashboard，适合简历展示 |
| **CN 网络友好** | 默认走 AiHubMix 代理，工具优先接国内服务 |
| **流式低延迟** | STT / LLM / TTS 三路并行 streaming，目标端到端 ≤ 500ms |

---

## §2 系统架构

```
┌─────────────────────────────────────────────────────┐
│                    游戏本（单机）                     │
│                                                     │
│  ┌──────────┐    ┌──────────────────────────────┐  │
│  │  感知层   │    │          推理层               │  │
│  │          │    │                              │  │
│  │ 唤醒词   │───▶│  LangGraph                   │  │
│  │ STT      │    │  draft → critic → respond    │  │
│  │ 人脸识别  │    │                              │  │
│  │ 声纹验证  │    │  ┌────────┐  ┌────────────┐  │  │
│  └──────────┘    │  │ 记忆   │  │  工具调用  │  │  │
│                  │  │ 读写   │  │  MCP tools │  │  │
│  ┌──────────┐    │  └────────┘  └────────────┘  │  │
│  │  输出层   │◀───│                              │  │
│  │          │    │  LiteLLM（模型路由）           │  │
│  │ TTS      │    └──────────────────────────────┘  │
│  │ 蓝牙音箱  │                                      │
│  └──────────┘    ┌──────────────────────────────┐  │
│                  │  支撑层                        │  │
│  ┌──────────┐    │  Security Guard / Rate Limit  │  │
│  │ 主动感知  │    │  Tracer / Dashboard           │  │
│  │ 定时扫描  │    │  Eval / Judge Ensemble        │  │
│  └──────────┘    └──────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

**数据流**：
```
麦克风 → openWakeWord（呼名触发） → Whisper STT
→ Security Guard → LangGraph（draft→critic→respond）
→ LiteLLM → 记忆读写 + MCP 工具调用
→ CosyVoice TTS → 蓝牙音箱
```

---

## §3 人格系统（Friends）

### 3.1 核心理念

人格不是「模式」，是「朋友」。每个人格：
- 有独立的名字、声音（CosyVoice 克隆）、性格、价值观、口头禅
- 有和你的独立关系史（私聊记忆）
- 通过「叫名字」触发，而不是用户手动切换模式

```
你说：「晓林，你觉得我应该换工作吗？」
→ 唤醒词 = 「晓林」→ 加载晓林人格 + 晓林的 L2 私聊记忆
→ 晓林以她的性格和你们的关系史回答
```

### 3.2 人格定义结构

```yaml
# personas/xiaolin/persona.yaml
name: 晓林
wake_word: 晓林          # 唤醒这个人格的词
voice_ref: voices/xiaolin_ref.wav
personality:
  traits: [稳重, 话少但精准, 不乱给建议]
  speaking_style: 句子短，停顿多，偶尔反问
  taboos: [不催促, 不比较别人]
  interests: [心理学, 城市规划, 纪录片]
knowledge_domain: 情感支持, 职业规划
system_prompt_template: personas/xiaolin/system.jinja2
```

### 3.3 社区人格包

人格可以打包为 `.persona` 格式（zip），包含 persona.yaml + system prompt + voice ref + 示例对话。
社区可以创作、上传、下载人格包——下载的不是皮肤，是一段潜在的关系。

```bash
# 未来 CLI
agent persona install xiaolin.persona
agent persona list
agent persona export xiaolin
```

---

## §4 记忆系统

### 4.1 三层架构

```
L1 工作记忆（Working Memory）
  ├── 当前对话上下文（最近 N 轮）
  ├── 范围：单次对话，对话结束丢弃
  └── 实现：LangGraph State（in-memory dict）

L2 情节记忆（Episodic Memory）—— 人格独立
  ├── 你和这个人格的对话历史、私下说过的话
  ├── 范围：per-persona，永久保存
  └── 实现：SQLite FTS5，表名带 persona_id 前缀

L3 长期记忆（Semantic Memory）—— 全人格共享
  ├── 关于你的核心事实：喜好、习惯、重要事件、情绪状态
  ├── 范围：global，所有人格均可读写
  └── 实现：SQLite，Dream 异步蒸馏写入
```

### 4.2 写入路由逻辑

对话结束后，记忆路由器决定写入哪一层：

```
信息类型                        → 写入层
─────────────────────────────────────────
情绪状态、重大事件、核心偏好      → L3（共享）
对话细节、私下心情、玩笑/梗       → L2（当前人格）
临时任务、当前话题                → L1（丢弃）
```

**类比**：你在朋友圈发「换工作了」→ 所有朋友（L3）都知道。
你只跟晓林说「其实我很怕失败」→ 只有晓林（L2）知道这一层。

### 4.3 Dream 蒸馏（L2→L3）

每晚异步运行，LLM 扫描当天所有人格的 L2 记忆，提炼出「关于你的新事实」沉淀到 L3。

```python
# backend/memory/dream.py
async def nightly_dream(persona_ids: list[str]) -> None:
    # 读各 persona L2 当天新增
    # LLM 抽取跨人格共性事实
    # 写入 L3 global store
```

---

## §5 语音管道（流式低延迟）

### 5.1 流水线

```
麦克风采集（连续）
    │
    ▼
openWakeWord（本地，<50ms 检测）
    │ 触发
    ▼
Whisper streaming STT（边说边转）
    │ 首词出现即发给 LLM
    ▼
LiteLLM streaming（边推理边生成 token）
    │ 首 token 出现即发给 TTS
    ▼
CosyVoice streaming TTS（边合成边播放）
    │
    ▼
蓝牙音箱
```

### 5.2 延迟预算

| 阶段 | 目标 |
|------|------|
| 唤醒词检测 | < 100ms |
| STT 首词延迟 | < 200ms |
| LLM 首 token | < 300ms |
| TTS 首音频块 | < 200ms |
| **端到端可感知延迟** | **< 500ms** |

### 5.3 情绪感知

STT 阶段同步分析声学特征（音量、语速、音调），输出情绪标签注入 LangGraph State：

```python
@dataclass
class EmotionContext:
    energy: float       # 0-1，疲惫到亢奋
    sentiment: str      # tired / neutral / excited
    speech_rate: float  # 字/秒
```

人格的 system prompt 根据情绪上下文动态调整语气、信息密度、回答长度。

---

## §6 主动感知（Proactive Agent）

不只是「你问我答」，还有主动触发：

### 6.1 定时扫描器

```python
# backend/proactive/scanner.py
# 每 5 分钟检查一次
async def proactive_scan(user_context: UserContext) -> list[ProactiveEvent]:
    events = []
    # 明天有早会 → 提醒早睡
    # 连续 3 周周一说累 → 问是否需要调整作息
    # 某个话题搁置超过 3 天 → 主动跟进
    return events
```

### 6.2 触发条件示例

| 触发 | 行为 |
|------|------|
| 用户到家（人脸识别） | 播放问候 + 当日摘要 |
| 明天有日历事件 | 今晚主动提醒 + 准备简报 |
| L3 检测到负面情绪连续 N 天 | 某个朋友主动问候 |
| 用户说过「提醒我 X」 | 到时间主动说 |

---

## §7 LLM 路由

保持原有 LiteLLM + AiHubMix 方案，补充：

```yaml
# backend/litellm/router.yaml
models:
  fast:        # 日常对话，低延迟优先
    primary: glm-5.1-free
    fallback: deepseek-chat
  reasoning:   # 复杂推理，质量优先
    primary: deepseek-r1
    fallback: claude-3-5-haiku
  local:       # 完全离线模式（可选）
    primary: ollama/qwen2.5:7b
```

路由规则：简单问答 → fast；tool calling / 多步推理 → reasoning；网络断开 → local（若已配置）。

---

## §8 工具层（MCP）

现有 7 个工具保留，新增规划：

| 工具 | 状态 | 说明 |
|------|------|------|
| bilibili | ✅ | 搜索/播放 |
| pyncm（网易云） | ✅ | 播放音乐 |
| bocha_search | ✅ | 网页搜索 |
| caldav | ✅ | 日历 |
| memory（MCP） | ✅ | 记忆读写 |
| weather | 待接 | 天气查询 |
| home_assistant | 待接 | 智能家居 |

所有工具遵循 MCP 标准，社区可提交 PR 贡献新工具。

---

## §9 安全

| 组件 | 功能 |
|------|------|
| SecurityGuard | 注入检测，untrusted 上下文隔离 |
| RateLimit | 防止 LLM API 超支 |
| CircuitBreaker | 外部服务熔断 |
| 声纹门禁 | 可选，识别主人声纹 |
| 人脸门禁 | 可选，识别主人面孔 |
| 审计日志 | 所有工具调用记录 |

---

## §10 评测体系

保留原有 5-LLM 陪审 + 720+ 用例框架，新增人格一致性维度：

**9 个评测维度**：

| 维度 | 说明 |
|------|------|
| 任务完成率 | tool calling 是否成功 |
| 工具使用准确性 | 参数正确性 |
| 记忆召回准确性 | L2/L3 读取正确 |
| 鲁棒性 | 边界输入处理 |
| 端到端延迟 | ≤ 500ms |
| API 成本 | token 效率 |
| **人格一致性** | 同一人格跨对话性格是否稳定 |
| 唤醒词准确率 | 召回 / 误触发 |
| 主人识别准确率 | 声纹 / 人脸 |

---

## §11 可观测性

```
backend/observe/
  tracer.py      # OpenTelemetry spans，覆盖每次 LLM 调用和工具调用
  dashboard.py   # SQLite 轻量 Web 看板
```

看板展示：对话历史、工具调用成功率、各人格使用频率、记忆写入量、延迟分布。

---

## §12 部署

### 单机 Docker Compose（主路径）

```yaml
# deploy/docker-compose.yml
services:
  agent:        # 主服务（LangGraph + 记忆 + 工具）
  dashboard:    # 可观测 Web UI
  dream:        # 夜间记忆蒸馏定时任务
  proactive:    # 主动感知定时扫描器
```

### 裸机运行（开发模式）

```bash
python main.py --persona xiaolin
python main.py --persona aze
```

### 硬件要求

| 组件 | 要求 |
|------|------|
| CPU | 4 核以上（Whisper 推理用） |
| RAM | 8GB+（推荐 16GB） |
| 摄像头 | USB，OpenCV 兼容 |
| 音箱 | 蓝牙或 USB |
| OS | Windows 11 / Ubuntu 22.04 |

---

## §13 文件结构

```
My_agent/
├── core/              # 共享类型、路由、熔断器
├── backend/
│   ├── litellm/       # LLM 客户端、路由配置
│   ├── memory/        # L1/L2/L3 存储、Dream 蒸馏
│   ├── orchestrator/  # LangGraph 图、工具调用
│   ├── security/      # 注入检测、限流
│   ├── observe/       # Tracing、Dashboard
│   ├── proactive/     # 主动感知扫描器（新增）
│   ├── mcp_servers/   # 7 个 MCP 工具实现
│   ├── tts/           # CosyVoice 客户端
│   └── eval/          # 5-LLM 陪审、校准
├── edge/              # 感知层（本机运行）
│   ├── wakeword.py    # openWakeWord
│   ├── face_gate.py   # 人脸识别
│   ├── voiceprint.py  # 声纹验证
│   └── audio_routing.py
├── personas/          # 人格定义
│   ├── _template/     # 新建人格模板
│   └── assistant/     # 默认助手人格
├── deploy/            # Docker Compose、systemd
├── tests/             # smoke_test.py（185 项）
├── eval/              # YAML 测试用例
├── docs/              # 文档
└── main.py            # 入口
```

---

## §14 路线图

| 阶段 | 目标 | 预计 |
|------|------|------|
| P0 | ✅ 代码框架 + 185 smoke 测试通过 | 完成 |
| P1 | 去 Pi：删 WireGuard/HAL，单机运行 | 1 周 |
| P2 | 人格系统重构：名字唤醒 + 独立记忆 | 1 周 |
| P3 | 流式管道：STT/LLM/TTS 并行 streaming | 2 周 |
| P4 | 主动感知：定时扫描 + 情绪感知 | 1 周 |
| P5 | 社区人格包格式 + 发布 | 1 周 |
| P6 | 完整评测 + README + 开源发布 | 1 周 |

---

*日期：2026-04-29*
