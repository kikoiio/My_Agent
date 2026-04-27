# My_agent — Pi 4B 24/7 多人格语音 Agent

完整设计见 [plan.md](plan.md)；当前实施进度见 [process.md](process.md)。

## 当前状态

8 个 batch 全部完成（88 文件），核心逻辑已通过 160 项冒烟测试。**尚未可端到端运行（需要 LLM API 密钥 + 树莓派硬件）。**

## 项目布局

详见 plan.md §13。本仓库已创建：

- `core/` — 平台无关核心（types、persona、router、breaker、HAL 接口）
- `core/hardware/` — HAL 抽象 + Null/Mock 实现
- `personas/_template/` — 人格 5 件套模板
- `data/` — 运行时 SQLite（不入库）
- `eval/fixtures/` — Mock HAL fixture（待填）

## 用户必填项

详见 plan.md 附录 A，关键项：

- LLM 提供商 API keys → `backend/secrets/llm_keys.env`
- 人格定义 → `personas/<Name>/{system_prompt.md, voice_ref.wav, voice_ref.txt, wake.onnx, tools.yaml}`
- 主人录入 → `python scripts/enroll_owner.py`（待 Batch 7 实现）
- 网易云 / B 站 / 飞书登录 → `python scripts/*_login.py`（待 Batch 7）

## 快速开始

### 1. 环境设置（开发机）

```bash
# Clone 项目
cd ~/projects
git clone https://github.com/your-org/multi-persona-voice-agent.git
cd My_agent

# 创建虚拟环境
python -m venv .venv
. .venv/Scripts/activate    # Windows
# . .venv/bin/activate     # Linux/macOS

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置 LLM 密钥

```bash
# 创建密钥文件
mkdir -p backend/secrets
cat > backend/secrets/llm_keys.env << EOF
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
COHERE_API_KEY=...
REPLICATE_API_KEY=...
EOF
chmod 600 backend/secrets/llm_keys.env
```

### 3. 创建第一个人格

```bash
# 使用模板创建人格目录
cp -r personas/_template personas/kobe

# 编辑人格文件（示例）
echo "你是 NBA 传奇球星 Kobe Bryant。" > personas/kobe/system_prompt.md
echo "Kobe 说话像 Kobe" > personas/kobe/voice_ref.txt
```

### 4. 运行评测（可选）

```bash
# 运行测试用例
pytest eval/runners/harness.py -v

# 生成报告
python eval/runners/reporter.py --output eval_report.html
```

### 5. 部署到树莓派

```bash
# 在树莓派上检查硬件
bash deploy/check_hardware.sh

# 安装 edge runtime
bash deploy/wireguard/setup.sh raspberrypi 192.168.1.100

# 启动 edge service
sudo systemctl start edge-runtime
sudo systemctl status edge-runtime
```

### 6. 注册主人（Pi 上）

```bash
# 录入主人人脸和声纹
python scripts/enroll_owner.py --owner-id owner

# 训练唤醒词
python scripts/wakeword_train.py kobe --samples 30

# 测试语音合成
python scripts/test_persona_voice.py kobe --text "你好，我是 Kobe"
```

## 开发依赖

详见 `requirements.txt`（Batch 1 基础）。后续 batch 会按需追加：

- **Batch 2**: fastapi（看板）
- **Batch 3**: pytest, deepeval, jinja2, litellm
- **Batch 4**: dashscope, pyncm, bilibili-api, browser-use
- **Batch 5**: pipecat, langgraph, langchain
- **Batch 6**: picamera2, sherpa-onnx, openwakeword, insightface, onnxruntime

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                   Backend (游戏本)                        │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────────┐ │
│  │ LangGraph│  │ Pipecat  │  │ Memory Store (SQLite)  │ │
│  │  draft   │  │ Pipeline │  │ L1/L2/L3 (dream)       │ │
│  │ ↓ critic │  │ STT→LLM  │  │ Tracer (observability) │ │
│  │ ↓respond │  │ →TTS     │  └────────────────────────┘ │
│  └──────────┘  └──────────┘           ↕                  │
│       ↑              ↑                  │                 │
│       ├──────────────┴──────────────────┤                 │
│       │         WebSocket Tunnel        │                 │
│       └────────────────┬─────────────────┘                 │
└─────────────────────────────────────────────────────────┘
                         │
          ┌──────────────┴──────────────┐
          │   WireGuard (encrypted)     │
          │   [10.0.0.2] ← → [10.0.0.1]│
          └──────────────┬──────────────┘
                         │
    ┌────────────────────┴─────────────────────┐
    │                                          │
┌───▼────────────────────────────────────────┐│
│        Edge Runtime (树莓派 4B)            ││
│  ┌────────────────────────────────────┐  ││
│  │  Camera (picamera2)                │  ││
│  │  Face Gate (InsightFace)           │  ││
│  │  Voice Gate (3D-Speaker)           │  ││
│  │  Wake Word (OpenWakeWord × N)      │  ││
│  │  Audio Router (PipeWire + BT)      │  ││
│  │  STT (Sherpa-ONNX)                 │  ││
│  └────────────────────────────────────┘  ││
└────────────────────────────────────────────┘│
                                              │
                   USB Camera, Mic, Speaker ──┘
```

## 核心概念

- **Persona**：独立的AI人格，有自己的system_prompt、声音、工具权限
- **Agent Loop**：单轮对话（route → LLM → memory）
- **LangGraph**：draft→critic→respond三层推理
- **Memory**：L1(会话)、L2(情景)、L3(梦境/整合)三层记忆
- **Tracer**：分布式追踪与judge评测
- **Guard**：安全守卫（注入检测、内容分类）
- **Hardware Abstraction**：Pi/远程硬件透明切换

## 文件结构

详见 [process.md](process.md) 和 [plan.md](plan.md) §13。

## 测试

```bash
# 运行冒烟测试（无需硬件/API密钥）
python -m pytest tests/smoke_test.py -v

# 运行评测用例（需要 LLM 密钥）
pytest eval/runners/harness.py -v

# 运行特定类别
pytest tests/smoke_test.py -k "security" -v
```

## 部署

- **Backend**: Docker Compose（`deploy/docker-compose.yml`）
- **Edge**: systemd 服务（`deploy/systemd/edge-runtime.service`）
- **Network**: WireGuard VPN（`deploy/wireguard/setup.sh`）

## 许可证

（添加你的许可证）
