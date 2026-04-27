# My_Agent 配置指南

> 本文档列出你需要自行配置的所有内容。

---

## 目录

1. [LLM API Keys](#1-llm-api-keys立即配置)
2. [Bilibili / 网易云登录](#2-bilibili--网易云音乐登录)
3. [CalDAV 日历](#3-caldav-日历)
4. [可选配置](#4-可选配置)

---

## 1. LLM API Keys（立即配置）

### 1.1 创建密钥文件

```bash
cp backend/secrets/env.example backend/secrets/llm_keys.env
```

编辑 `backend/secrets/llm_keys.env`，填入 API Key：

| 变量 | 来源 | 说明 |
|------|------|------|
| `AIHUBMIX_API_KEY` | [aihubmix.com](https://aihubmix.com) 注册 → 控制台获取 | 国内直连，有免费模型 |
| `NVIDIA_API_KEY` | [build.nvidia.com](https://build.nvidia.com) 注册 → API Keys 生成 | 国内直连，送 credits |
| `DASHSCOPE_API_KEY` | [阿里云百炼](https://dashscope.aliyun.com) | 可选，用于 CosyVoice TTS |

### 1.2 配置 LLM 路由

编辑 `backend/litellm/router.yaml`，把 `<user-model>` 替换为实际模型名：

```yaml
model_list:
  - model_name: default_fast       # 日常对话
    litellm_params:
      model: openai/你的模型名
      api_base: https://aihubmix.com/v1
      api_key: ${AIHUBMIX_API_KEY}
```

免费模型参考（以 aihubmix 为例）：
- `gpt-4.1-free` — GPT-4.1 免费版
- `coding-glm-5-free` — GLM-5 免费版
- `gemini-3-flash-preview-free` — Gemini 3 免费版

NVIDIA 免费模型参考（build.nvidia.com 浏览）：
- `meta/llama-3.1-8b-instruct`
- `deepseek/deepseek-v4-flash`
- `mistralai/mistral-large`

### 1.3 验证

```bash
python -c "
from litellm import Router
import yaml
with open('backend/litellm/router.yaml') as f:
    config = yaml.safe_load(f)
router = Router(model_list=config['model_list'])
print(f'✅ 路由加载成功：{len(config[\"model_list\"])} 个模型')
"
```

---

## 2. Bilibili / 网易云音乐登录

### 2.1 Bilibili

```bash
pip install bilibili-api-python
python scripts/bilibili_qr_login.py --timeout 120
```

扫码成功后凭据保存在 `backend/secrets/bilibili_credential.json`。

### 2.2 网易云音乐

```bash
pip install pyncm
python scripts/ncm_qr_login.py --timeout 120
```

扫码成功后凭据保存在 `backend/secrets/ncm_credential.json`。

---

## 3. CalDAV 日历

编辑 `backend/secrets/llm_keys.env`，添加以下内容：

```env
CALDAV_URL=https://你的-caldav-服务器.com/caldav.php/
CALDAV_USERNAME=你的用户名
CALDAV_PASSWORD=你的密码
```

### 免费 CalDAV 服务推荐

| 服务 | 地址 | 说明 |
|------|------|------|
| **QQ 邮箱日历** | `https://caldav.qq.com` | 用户名填 QQ 号，最稳定 |
| **iCloud 日历** | `https://caldav.icloud.com` | Apple 用户自带 |

---

## 4. 可选配置

| 功能 | 配置方式 | 费用 |
|------|---------|------|
| **TTS 语音合成** | `DASHSCOPE_API_KEY`（阿里云 DashScope） | 每月免费额度 |
| **TTS 离线备选** | 无需配置，`backend/tts/piper_client.py` 本地运行 | 永久免费 |
| **网页搜索** | `BOCHA_API_KEY`（Bocha 注册） | 注册送免费额度 |
| **飞书通知** | `LARK_APP_ID` + `LARK_APP_SECRET` | 自建应用免费 |
| **Docker 部署** | `docker compose up -d` | 免费 |
| **WireGuard VPN** | `bash deploy/wireguard/setup.sh` | 免费 |
| **Memos 云端记忆** | 不配置即可，SQLite 本地已够用 | 免费 |

### 无需配置（开箱即用）

| 功能 | 说明 |
|------|------|
| **数据库** | SQLite + WAL 模式，零运维，单文件备份 |
| **记忆系统** | L1/L2/L3 三层，DreamWorker 自动整理 |
| **人格路由** | 按消息长度和关键词自动路由到不同模型 |

---

## 验证清单

```bash
# 1. 环境变量
python -c "
from dotenv import load_dotenv
load_dotenv('backend/secrets/llm_keys.env')
import os
for k in ['AIHUBMIX_API_KEY', 'NVIDIA_API_KEY', 'CALDAV_URL']:
    print(f'{k}: {\"✅\" if os.getenv(k) else \"❌\"}')"

# 2. SQLite WAL
python -c "
import sqlite3
conn = sqlite3.connect(':memory:')
conn.execute('PRAGMA journal_mode=WAL')
print('✅ SQLite WAL 支持')"
```

---

*最后更新：2026-04-27*
