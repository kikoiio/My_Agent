# My Agent — 本地语音 AI 伴侣

[![Tests](https://img.shields.io/badge/tests-257%20passing-brightgreen)](tests/smoke_test.py)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)

本地优先、可自托管的多人格语音 AI 伴侣。每个人格是一位有独立名字、声音、性格和私人记忆的**朋友**。呼名触发，支持工具调用（B 站、网易云、日历、网页搜索），记忆持久化。无需云端依赖，单机运行。

---

## 快速开始

**1. 安装依赖**

```bash
git clone <repo-url>
cd My_agent
pip install -r requirements.txt
```

**2. 配置密钥**

```bash
cp backend/secrets/llm_keys.env.example backend/secrets/llm_keys.env
# 填入 AIHUBMIX_API_KEY（必须）和 NVIDIA_API_KEY（可选）

cp backend/secrets/accounts.env.example backend/secrets/accounts.env
# 可选：填入 B 站 / 网易云 cookie 以启用媒体工具
```

**3. 启动 CLI 对话**

```bash
python main.py                      # 默认人格（小安）
python main.py --persona xiaolin    # 切换到晓林人格
```

**4. 运行测试**

```bash
python -m pytest tests/smoke_test.py -v   # 257 个测试，全绿
```

**5. Docker 部署（可选）**

```bash
docker compose -f deploy/docker-compose.yml up -d
```

---

## 架构

```
单机（游戏本 / 台式机）
  edge/                          backend/
    wakeword.py  ← 呼名触发         orchestrator/graph.py  ← LangGraph draft→critic→respond
    face_gate.py ← 人脸识别         litellm/client.py      ← 模型路由（AIHubMix）
    emotion.py   ← 声学特征         memory/store.py        ← 3 层 SQLite 记忆
         │                          security/guard.py      ← 注入防御 + 频率限制
         │  进程内直接调用           mcp_servers/           ← 7 个工具（B 站/网易云/日历/搜索…）
         └──────────────────────    proactive/scanner.py   ← 主动感知（5 分钟扫描）
                core/ (shared types, persona loading, circuit breaker)
                personas/ (人格定义：assistant / xiaolin / 你自己的…)
                tools/ (persona_pack.py — 人格打包 / 安装 / 验证)
```

**数据流：** 语音 → openWakeWord（人格名触发）→ Whisper STT → LangGraph → LiteLLM → CosyVoice TTS → 音箱。

**记忆层：**
- L1（全局）：系统级上下文，永久保留
- L2（人格私有）：每个人格与用户的情节记忆，按 `persona_id` 隔离
- L3（全局语义）：Dream 异步蒸馏 L2→L3，所有人格共享

---

## 人格系统

每个人格是 `personas/<name>/` 目录下的一组文件：

| 文件 | 作用 |
|------|------|
| `persona.yaml` | 名字、唤醒词、简介 |
| `system.jinja2` 或 `system_prompt.md` | 性格、说话方式、禁忌 |
| `voices/ref.wav` | CosyVoice 零样本声音克隆参考音 |
| `tools.yaml` | 工具白名单 / 黑名单 / 高危验证列表 |
| `routing.yaml` | 模型路由偏好（可选） |
| `memory_init.json` | 初始记忆（可选） |

**打包分享：**

```bash
python tools/persona_pack.py pack personas/xiaolin    # → xiaolin.persona
python tools/persona_pack.py install xiaolin.persona  # → 解压到 personas/
python tools/persona_pack.py validate xiaolin.persona # → 格式检查
```

详见 [docs/persona-guide.md](docs/persona-guide.md)。

---

## 工具列表

| 工具组 | 功能 |
|--------|------|
| `bilibili_*` | 查直播间信息、拉弹幕快照 |
| `pyncm_*` | 网易云搜歌、查歌单、获取播放列表 |
| `caldav_*` | 日历事件查询 / 创建 / 删除 |
| `bocha_*` | 网页搜索、新闻搜索、图片搜索 |
| `memory_*` | 记忆召回、写入、摘要 |

工具调用经过人格白名单过滤；高危操作（发弹幕、删日历、记忆写入）需主人声纹二次验证。

---

## 评测

参见 [eval/report.md](eval/report.md)，涵盖 9 个维度：任务完成、安全防注入、记忆召回、工具调用、人格一致性、情绪感知、流式延迟（存根）、主动感知、语音生物特征。

---

## 贡献

欢迎提交工具、人格包、bug 修复，详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 许可证

[Apache 2.0](LICENSE)
