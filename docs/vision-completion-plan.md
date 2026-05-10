# 愿景完成计划 (P7–P12)

> **创建日期**：2026-05-10
> **目标**：从 "P1–P6 基础设施完成" 推进到 "plan.md §0 愿景完整实现"。
> **前置条件**：P1–P6 全部完成（281 smoke tests 全绿）；硬件已到位（蓝牙音箱 + USB 网络摄像头自带麦）。
> **权威设计**：`plan.md`（v2，2026-04-29）。本文件是 plan.md 落地到代码 + 实机的执行清单。

---

## 现状盘点（2026-05-10）

### ✅ 已完成（基础设施层）

- 文字对话 + 26 工具调用（AIHubMix 真实验证）
- STT/TTS/wake/face/voiceprint 模块**代码已写真**（非 stub），但仅在 mock 下测试
- 281 smoke tests 全绿（含硬件 mocked 路径）
- L1/L2/L3 三层记忆 + Dream 蒸馏（FTS5 全文检索）
- 主动感知扫描器（`proactive_scan()`）能产出事件
- 5-LLM 评委 + 校准探针框架就位
- `.persona` 包格式 + 打包/安装/校验 CLI
- Docker Compose / GitHub Actions / LICENSE / README 就绪

### ⚠️ 已写代码但**未在真实硬件上验证过**

| 模块 | 文件 | 阻塞点 |
|------|------|-------|
| 实时 STT | [`backend/streaming/pipeline.py`](backend/streaming/pipeline.py) `_transcribe()` | 未在真实 USB 麦克风采到的音频上跑过 |
| 实时 TTS 播放 | [`backend/tts/__init__.py`](backend/tts/__init__.py) `play_audio_mp3()` | 未在真实蓝牙音箱上验证过 |
| 唤醒词 | [`edge/wakeword.py`](edge/wakeword.py) `WakeWordListener.listen()` | 未在嘈杂环境中测试过 |
| 人脸识别 | [`edge/face_gate.py`](edge/face_gate.py) `verify()` | 未用真实 owner 注册过 |
| 声纹验证 | [`edge/voiceprint.py`](edge/voiceprint.py) `verify()` | 未用真实 owner 注册过 |
| 端到端语音回路 | [`main.py`](main.py) `_voice_loop()` | 整条链路未跑通 |

### ❌ 仍是真存根 / 未接线

| 模块 | 文件 | 现状 | 应有 |
|------|------|------|------|
| 情绪感知 | [`edge/emotion.py`](edge/emotion.py) | 始终返回 `neutral / valence=0` | librosa 声学特征 → 真实 valence/arousal/tone |
| 流式 LLM→TTS | [`backend/streaming/pipeline.py`](backend/streaming/pipeline.py) | 三阶段管道结构存在但 `_voice_loop` 是 batched | 真流式 token-by-token，TTS 句级切块送音箱 |
| 主动事件分发 | [`backend/proactive/scanner.py`](backend/proactive/scanner.py) | `proactive_scan()` 产出事件后无人消费 | voice loop 后台 task 拉事件 → TTS 播放 |
| `on_arrival` 接线 | [`edge/face_gate.py`](edge/face_gate.py) | 回调签名存在，无人注入 | voice loop 启动时注入回调 → 触发"到家"事件 |
| 声纹门禁 | [`main.py`](main.py) `_voice_loop()` | `speaker_verified=False` 硬编码 | 第一次唤醒时调 `voiceprint.verify()`，过则放行高危工具 |
| 多人格音色 | [`backend/tts/edge_tts_client.py`](backend/tts/edge_tts_client.py) | 全局 `zh-CN-XiaoxiaoNeural` 一种声音 | persona.yaml `voice_name` 字段 → 不同 edge-tts voice |
| 向量记忆 | [`backend/memory/store.py`](backend/memory/store.py) | 仅 FTS5 关键词 | BGE-M3 embedding + 混合检索 |
| `EmotionContext` 注入 graph | [`backend/orchestrator/graph.py`](backend/orchestrator/graph.py) | 不读 emotion 字段 | system prompt 加入 `{{emotion_hint}}`，由 EmotionExtractor 写 state |
| Dashboard 实跑 | [`backend/observe/dashboard.py`](backend/observe/dashboard.py) | 代码存在，未启动 | docker compose 起来后 UI 可访问 |
| 真实 eval 跑分 | [`eval/runners/harness.py`](eval/runners/harness.py) | 框架就位 | 跑全部 yaml 用例，9 维度分数写入 `eval/report.md` |

---

## 计划总览

| 阶段 | 主题 | 关键交付 | 估时 | 优先级 |
|------|------|---------|------|--------|
| **P7** | 实机端到端验证 | 蓝牙音箱 + 摄像头 + 麦克风跑通 wake→STT→LLM→TTS 全链路 | 1–2 天 | 🔴 立即 |
| **P8** | 主动感知接线 | 事件分发 + 到家问候 + 后台轮询 | 1 天 | 🔴 高 |
| **P9** | 情绪感知激活 | librosa 声学特征 → EmotionContext → system prompt | 1–2 天 | 🟡 中 |
| **P10** | 流式低延迟 | 真流式 STT/LLM/TTS 三路并行，目标 < 500ms | 2–3 天 | 🟡 中 |
| **P11** | 多人格音色 + 声纹门禁 | 每个 persona 不同声音；声纹激活高危工具 | 1–2 天 | 🟡 中 |
| **P12** | 向量记忆 + 真实评测 + 完整部署 | BGE-M3 接入；5-LLM 跑全量 yaml；Docker / CI 全绿 | 2–3 天 | 🟢 低 |

完成 P7–P12 即对齐 plan.md §0 全部愿景。

---

## P7：实机端到端验证 🔴

**目标**：plan.md §0 描述的"叫名字 → 它回应"在真实硬件上跑通。

### P7.1 硬件准备 ✅ (2026-05-10)

- [x] 蓝牙音箱已配对（btha2dp [25/27]，未设为默认输出 — 当前默认是 Philips USB [4]）
- [x] USB C922 摄像头自带麦识别为默认输入 [1]
- [x] `python scripts/check_devices.py` 列出 37 个 sounddevice 入口、2 个摄像头
- [x] `python scripts/check_devices.py --beep` 1 秒 440Hz 蜂鸣已发声
- [x] **修了 Windows 11 全局摄像头权限 Deny**：`HKLM\...\webcam\Value` 改 Allow

### P7.2 依赖安装 ✅ (2026-05-10)

```bash
pip install -r requirements-voice.txt
pip install opencv-python==4.10.0.84   # 4.13 在 Py3.14 + Win11 上 MSMF 有回归
pip uninstall -y opencv-python-headless # 必须用完整版才能 cv2.imshow + DirectShow
```

**Python 3.14 wheel 现已全面可用**（torch 2.11.0 / faster-whisper 1.2.1 / ctranslate2 4.7.1 / insightface 0.7.3 / resemblyzer 0.1.4）。CLAUDE.md / requirements-voice.txt 顶部"3.14 暂未支持"的提示已过时。

### P7.3 Owner 注册 ✅ (2026-05-10)

```bash
python scripts/enroll_owner.py --camera-index 1   # 1 = USB C922
```

人脸 5 张 + 声纹 3 段 → `data/enrollments/{faces,voices}/owner.npy`。

**修了 3 个真坑**（详见 `docs/project-memory.md` session log）：
1. opencv-python-headless 不带 GUI 后端 + opencv 4.13 在 Py3.14 上 MSMF 回归 → 装 opencv-python 4.10.0
2. sounddevice 在 Win11 上 MME/DirectSound/WASAPI 都打不开 C922 麦，只有 **WDM-KS [28]** 行 → `edge/audio_capture.py` 加 hostapi 优先级 (WDM-KS > WASAPI > DirectSound > MME)
3. resemblyzer 0.1.4 `preprocess_wav` 不收 BytesIO → `edge/voiceprint.py::_load_wav` 用 stdlib wave 自己解码成 ndarray 再传

### P7.4 端到端语音对话

```bash
python main.py --persona assistant --voice
```

测试用例（每个跑 3 次取均值）：

| 用例 | 输入 | 期望行为 | 测项 |
|------|------|---------|------|
| 1. 直答 | "小安，你好" | TTS 播放问候 | 唤醒成功率，TTS 清晰度 |
| 2. 工具调用 | "小安，搜下《七里香》" | 调 `pyncm_search_track` + 播报结果 | 工具识别，输出可读 |
| 3. 工具+追问 | "小安，1 号直播间在播什么？" "持续多久了？" | 两轮 tool calling，记忆带过 | L1 上下文延续 |
| 4. 长回复 | "小安，给我讲个故事" | TTS 播放 ≥ 30s 音频 | 流畅度，无中断 |
| 5. 多人格 | "晓林，最近怎么样？" | 切到晓林人格 + 不同声音 | wake_word 路由 |

### P7.5 延迟测量

在 `_voice_loop` 各阶段加 `time.perf_counter()` 打点，输出到 stderr。跑 10 轮取中位数：

| 阶段 | 当前预期 | 目标 (P10 优化后) |
|------|----------|-----------------|
| 唤醒检测 | 200–400ms | < 100ms |
| STT (base 模型) | 800–1500ms | < 300ms（streaming） |
| LLM 首 token | 600–1200ms | < 300ms（AIHubMix 网络） |
| TTS 首块 | 400–800ms | < 200ms（streaming） |
| **端到端** | 2.0–3.5s | **< 500ms** |

记录到 `eval/report.md` § 7 流式延迟。

### P7.6 调优决策点

- 若 STT > 1.5s：Whisper `base` → `tiny`（精度可能下降）
- 若 TTS 不清楚：换 edge-tts voice（`zh-CN-YunjianNeural` / `zh-CN-XiaoyiNeural`）
- 若唤醒漏触：降低 `_KEYWORD_CONFIDENCE_THRESHOLD`，加更多别名
- 若蓝牙延迟感人（>1s）：换 USB 音箱或线材

### P7.7 验收

- [ ] 5 个用例全部跑通（≥ 80% 成功率）
- [ ] 延迟数字写入 `eval/report.md`
- [ ] `docs/project-memory.md` 加 session log，附实测照片/录音（可选）
- [ ] 281/281 smoke tests 仍全绿

---

## P8：主动感知接线 🔴

**目标**：plan.md §6 描述的"它知道你说随便的时候通常不太好"等场景生效。

### P8.1 事件分发器

新建 `backend/proactive/dispatcher.py`：

```python
class ProactiveDispatcher:
    """Background task that polls scanner and queues TTS events."""
    def __init__(self, store, persona, tts_client, on_speak: Callable[[str], Awaitable[None]]):
        self.queue: asyncio.Queue[ProactiveEvent] = asyncio.Queue()
        ...
    async def run(self, interval_sec: int = 300) -> None:
        # 每 5 分钟 proactive_scan，事件入队
    async def speak_loop(self, idle_threshold_sec: int = 30) -> None:
        # 等用户空闲 30s → 播放最高优先级事件
```

### P8.2 voice_loop 集成

`main.py::_voice_loop` 启动 3 个并行 task：

```python
async with asyncio.TaskGroup() as tg:
    tg.create_task(_main_voice_loop(...))            # 现有 wake→STT→LLM→TTS
    tg.create_task(dispatcher.run(interval_sec=300)) # 后台扫描
    tg.create_task(dispatcher.speak_loop())          # 空闲时播事件
```

### P8.3 face_gate on_arrival 接线

```python
# main.py
async def on_owner_arrival(user_id: str, confidence: float):
    event = check_home_arrival(confidence, user_id, persona.name)
    if event:
        await dispatcher.queue.put(event)

face_gate = FaceGate(on_arrival=on_owner_arrival)
# 启一个常驻 task：每 N 秒抓一帧、verify、调 on_arrival
tg.create_task(face_gate.run_continuous_check(interval_sec=10))
```

需要在 `edge/face_gate.py` 加 `run_continuous_check()` 方法（OpenCV 抓帧 + verify 循环）。

### P8.4 Dream 写入情绪趋势

`backend/memory/dream.py` 增强：每晚扫 L2，提取每日情绪聚合（`avg_valence`, `dominant_tone`），写入 `dreams` 表的 `summary` 字段。让 `query_emotion_trend()` 能查到真实数据。

### P8.5 验收

- [ ] 启动 voice loop 后，等 5 分钟看 stderr 有 `[proactive] scanned 0 events` 类日志
- [ ] 模拟连续 3 天负面记忆（手动 SQL 插入 dreams），重启后第一次空闲触发 `check_emotion_trend` 事件并 TTS 播报
- [ ] 离开摄像头视野 30s 再回来，触发"到家"问候
- [ ] 新增 4 个 smoke tests（`TestProactiveDispatcher`），保持 285/285 绿

---

## P9：情绪感知激活 🟡

**目标**：plan.md §5.3 — 系统能"听出你不太好"。

### P9.1 librosa 特征提取

替换 [`edge/emotion.py`](edge/emotion.py) 存根：

```python
import librosa
import numpy as np

async def extract(self, audio_chunk: bytes) -> EmotionContext:
    arr = np.frombuffer(audio_chunk, dtype=np.float32)
    rms = float(librosa.feature.rms(y=arr).mean())          # 0–1
    f0 = librosa.yin(arr, fmin=80, fmax=400, sr=16000)
    pitch_mean = float(np.nanmean(f0))                       # Hz
    pitch_std = float(np.nanstd(f0))                         # 抖动 → 紧张

    # 规则映射（先用启发式，留 ML 钩子）
    valence = self._map_valence(rms, pitch_mean)             # 高 pitch + 中 rms → 积极
    arousal = min(1.0, rms * 2.5)                            # 大声 → 高 arousal
    tone = self._classify_tone(valence, arousal, pitch_std)  # tired / neutral / excited / anxious
    return EmotionContext(persona="", valence=valence, arousal=arousal, tone=tone, ts=time.time())
```

**注**：先用规则映射做 baseline，留接口换 wav2vec2 微调模型。

### P9.2 注入 LangGraph

[`core/types.py`](core/types.py) `AgentState` 加 `emotion: EmotionContext | None = None`。

[`backend/orchestrator/graph.py`](backend/orchestrator/graph.py) `draft_node` 把 `state.emotion.tone` 拼入 system prompt：

```jinja
{{ system_prompt }}
{% if emotion and emotion.tone != "neutral" %}
[用户当前情绪：{{ emotion.tone }}（valence={{ emotion.valence|round(2) }}）。请用相应的语气和信息密度回应。]
{% endif %}
```

### P9.3 voice_loop 注入

```python
# main.py _voice_loop
emotion = await emotion_extractor.extract(audio_pcm_bytes)
state = await run_graph(graph, ..., emotion=emotion)
```

### P9.4 persona system.jinja2 利用情绪

更新 `personas/assistant/system.jinja2` 和 `personas/xiaolin/system.jinja2`，增加情绪条件分支（短句/共情语等）。

### P9.5 验收

- [ ] 跑录音"今天好累"（低 pitch + 低 rms）→ tone=tired，回复带共情
- [ ] 跑录音"我升职了！"（高 pitch + 高 rms）→ tone=excited，回复带兴奋
- [ ] 新增 6 个 smoke tests（mocked librosa），保持 291/291 绿

---

## P10：流式低延迟 < 500ms 🟡

**目标**：plan.md §5.1–5.2 — 三路并行流式，端到端可感知延迟 ≤ 500ms。

### P10.1 流式 STT

faster-whisper 已支持 partial transcripts。改 [`backend/streaming/pipeline.py`](backend/streaming/pipeline.py) `_stt_stage`：

```python
# 用 vad_filter + 边录边转
async def _stt_stage_streaming(audio_stream, out_queue):
    buffer = []
    async for chunk in audio_stream:
        buffer.append(chunk)
        if _enough_audio(buffer):  # 0.5s 累一次
            partial = await _transcribe_partial(buffer[-N:])
            await out_queue.put(partial)
```

### P10.2 流式 LLM

`backend/litellm/client.py` 已有 `create_llm_stream()`。改 graph 的 `respond_node`：

```python
async for token in llm_stream(messages):
    await tts_input_queue.put(token)
    if _is_sentence_end(token):
        # 句号即冲到 TTS
        await tts_input_queue.put(_SENTENCE_BOUNDARY)
```

### P10.3 流式 TTS

edge-tts 原生支持 chunked。改 [`backend/tts/edge_tts_client.py`](backend/tts/edge_tts_client.py) 加 `synthesize_stream()`，输出 mp3 chunk async generator。

播放端用 miniaudio 的 streaming decoder（已部分实现）。

### P10.4 voice_loop 全流式重写

```python
# main.py 新建 _voice_loop_streaming
async def _voice_loop_streaming(graph, persona, tracer):
    async for wake_event in listener.listen(stream_microphone()):
        result = await run_pipeline(
            audio_stream=mic_stream_until_silence(),
            persona_id=persona.name,
            llm_stream_fn=llm_stream,
            tts_stream_fn=tts_client.synthesize_stream,
            on_audio=speaker.play_chunk,
        )
        # result.latencies 记录到 tracer
```

保留旧 `_voice_loop` 作为 `--no-stream` fallback。

### P10.5 端到端延迟测量

`run_pipeline` 已经有 `latencies: dict[str, float]`。每次对话写入 tracer，dashboard 出 P50/P95 分布图。

### P10.6 验收

- [ ] 跑 20 轮短问答，端到端 P50 < 500ms
- [ ] 长回复时音箱不停顿（chunk 间隔 < 100ms）
- [ ] `eval/report.md` § 7 流式延迟改为 ✅ 实测
- [ ] smoke tests 不退化

---

## P11：多人格音色 + 声纹门禁 🟡

**目标**：plan.md §3 — 每个朋友有自己的声音；plan.md §9 — 高危工具的声纹门禁真实生效。

### P11.1 persona.yaml 加 voice 字段

```yaml
# personas/xiaolin/persona.yaml
name: 晓林
wake_word: 晓林
voice:
  edge_tts: zh-CN-XiaoyiNeural    # 短期方案
  cosyvoice_ref: voices/ref.wav    # 长期方案（部署 CosyVoice 后用）
```

[`core/persona.py`](core/persona.py) 加 `voice_name: str | None`、`voice_ref: Path | None` 字段。

### P11.2 EdgeTTSClient 接受 voice 参数

```python
class EdgeTTSClient:
    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural"): ...
    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        # voice override
```

`_voice_loop` 启动时按 persona 实例化对应 voice 的 client。

### P11.3 推荐音色映射

| Persona | edge-tts voice | 性格契合 |
|---------|----------------|---------|
| assistant (小安) | `zh-CN-XiaoxiaoNeural` | 温和默认 |
| xiaolin (晓林) | `zh-CN-XiaoyiNeural` | 稳重女声 |
| (新人格示例) | `zh-CN-YunjianNeural` | 沉稳男声 |
| (新人格示例) | `zh-CN-YunxiaNeural` | 活泼少年 |

### P11.4 CosyVoice 自托管（可选）

部署 [CosyVoice](https://github.com/FunAudioLLM/CosyVoice) 服务到本地（需 GPU 或忍受 CPU 慢）。`backend/tts/cosyvoice_client.py` 已有 `_synthesize_self_hosted()`，配置 `COSYVOICE_URL` env 即启用。

不部署也行，edge-tts 的 8 种中文声音够用。

### P11.5 声纹门禁激活

`main.py::_voice_loop`：

```python
voiceprint = VoicePrintGate()
await voiceprint.load_models()
session_speaker_verified = False

async for wake_event in listener.listen(...):
    audio = await capture_until_silence(...)
    if not session_speaker_verified:
        session_speaker_verified = await voiceprint.verify(audio)
        if session_speaker_verified:
            print("[声纹] 主人识别成功")
    state = await run_graph(graph, ..., speaker_verified=session_speaker_verified)
```

session_speaker_verified 在 5 分钟无动作后重置（防离开后被冒名）。

### P11.6 验收

- [ ] 三个 persona 各放一段 TTS，听感不同
- [ ] 主人本人喊唤醒词 → speaker_verified=True，发弹幕等高危工具可见
- [ ] 朋友冒名喊唤醒词 → speaker_verified=False，高危工具被隐藏
- [ ] 5 分钟无动作后再喊，重新声纹验证

---

## P12：向量记忆 + 真实评测 + 完整部署 🟢

**目标**：plan.md §10–§12 — 完整可观测、可评测、可部署。

### P12.1 向量记忆接入

[`backend/memory/store.py`](backend/memory/store.py) L2/L3 表加 `embedding BLOB` 字段。写入时用已存在的 `EmbeddingProvider`（BGE-M3）算 embedding，存为 numpy bytes。

查询时用混合检索：

```python
def search(self, query: str, top_k: int = 5):
    fts_results = self._fts5_search(query, top_k * 2)
    vec_results = self._vector_search(self.embedder.embed(query), top_k * 2)
    return self._reciprocal_rank_fusion(fts_results, vec_results)[:top_k]
```

### P12.2 Dashboard 实跑

```bash
docker compose -f deploy/docker-compose.yml up dashboard
# 浏览器开 http://localhost:8080
```

验证看板能显示：对话历史、工具调用成功率、各人格使用频率、记忆写入量、延迟分布（来自 P10 的 latencies）。

### P12.3 5-LLM 评委真实跑分

```bash
python -m eval.runners.harness --suite all --output eval/results/$(date +%Y%m%d).html
```

跑 `eval/cases/` 下全部 yaml 用例。把 9 维度分数写入 `eval/report.md`。

### P12.4 Docker Compose 全栈实测

```bash
docker compose -f deploy/docker-compose.yml up -d
# 4 个 service：agent, dashboard, dream, proactive
docker compose ps   # 全 healthy
docker compose logs -f
```

### P12.5 CI/CD 触发

```bash
git push origin main
# 看 GitHub Actions: 281+ tests on Python 3.11 + 3.12 全绿
```

### P12.6 验收

- [ ] L2 召回测试中"语义近义"的命中率 > 70%（FTS5 baseline 30%）
- [ ] dashboard 展示昨日所有指标，无空数据
- [ ] eval/report.md 9 维度全部 ✅ 真实分数
- [ ] docker compose 4 个服务全部 healthy 12 小时无 crash
- [ ] GitHub Actions 上 main 分支最近 commit 绿

---

## 完成判定

P7–P12 全部验收通过后：

```bash
python main.py --persona xiaolin --voice
# 1. "晓林" → 晓林声音回应，记忆写入 episodic_xiaolin
# 2. 表情低落地说 → 系统识别 tone=sad，回复带共情
# 3. 第一次唤醒后声纹验证通过，能发 B 站弹幕
# 4. 离开摄像头 30s 回来 → 主动问候 + 当日摘要
# 5. 端到端延迟 < 500ms
# 6. 记忆查询能用语义召回（"工作压力" 命中之前说的"老板今天又催我了"）
```

⇒ plan.md §0 愿景达成。

---

## 贯穿原则

- **每阶段结束 smoke tests 必须保持全绿**（当前 281）
- **每阶段结束更新 `docs/project-memory.md` session log**（带实测数据）
- **延迟相关改动用 tracer 打点 + dashboard 观测**，不靠主观感觉
- **新增模块必带测试**：mocked 硬件 + 关键路径
- **plan.md 是设计权威**，本文件改动若与 plan.md 冲突，以 plan.md 为准
- **Vision 检查表**：每次 PR 描述里勾选影响的愿景条目（朋友感 / 记忆 / 主动 / 流式 / 多人格）

---

## 估时与里程碑

| 里程碑 | 内容 | 累计天数 |
|--------|------|----------|
| **M1：能说话** | P7 完成，端到端语音回路跑通 | 2 |
| **M2：主动感** | P8 完成，能主动问候 | 3 |
| **M3：能听情绪** | P9 完成，识别 tone 并共情 | 5 |
| **M4：低延迟** | P10 完成，对话像真人 | 8 |
| **M5：多朋友** | P11 完成，每个 persona 不同声音 + 声纹保护 | 10 |
| **M6：愿景达成** | P12 完成，完整开源就绪 | 13 |

按 1 人独立开发节奏估，含调试和写文档时间。

---

*下一步：先做 P7.1 — 蓝牙音箱配对验证。*
