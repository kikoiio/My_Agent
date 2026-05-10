#!/usr/bin/env python3
"""Multi-Persona Voice Agent — CLI entry point.

Usage:
    python main.py [--persona assistant]           # text chat
    python main.py [--persona assistant] --voice   # voice chat (requires hardware)

Type messages to chat with the agent. /quit to exit.
"""

from __future__ import annotations

import asyncio
import argparse
import logging
import os
import time
import uuid
from pathlib import Path

from core.persona import load as load_persona
from backend.litellm.client import create_llm_callable, create_llm_callable_with_tools
from backend.memory.store import MemoryStore
from backend.observe.tracer import Tracer
from backend.orchestrator.graph import build_main_graph, run_graph
from backend.orchestrator.tools import ToolRegistry
from backend.security.guard import Guard

PROJECT_ROOT = Path(__file__).resolve().parent
SECRETS_DIR = PROJECT_ROOT / "backend" / "secrets"


def _build_tool_registry(memory_store: MemoryStore) -> ToolRegistry:
    """Wire whichever MCP servers have credentials configured.

    Servers without credentials are passed as ``None``; the registry will
    automatically hide their tools from the LLM.
    """
    bilibili = pyncm = caldav = bocha = None

    bili_cred = SECRETS_DIR / "bilibili_credential.json"
    if bili_cred.exists():
        try:
            from backend.mcp_servers.bilibili import BilibiliServer
            bilibili = BilibiliServer(credential_file=str(bili_cred))
            if not bilibili.authenticated:
                bilibili = None
        except Exception as e:
            logging.getLogger(__name__).warning("BilibiliServer init failed: %r", e)

    pyncm_cred = SECRETS_DIR / "pyncm_credential.json"
    if pyncm_cred.exists():
        try:
            from backend.mcp_servers.pyncm import PyncmServer
            pyncm = PyncmServer(credential_file=str(pyncm_cred))
            if not pyncm.authenticated:
                pyncm = None
        except Exception as e:
            logging.getLogger(__name__).warning("PyncmServer init failed: %r", e)

    caldav_url = os.environ.get("CALDAV_URL")
    caldav_user = os.environ.get("CALDAV_USERNAME")
    caldav_pw = os.environ.get("CALDAV_PASSWORD")
    if caldav_url and caldav_user and caldav_pw:
        try:
            from backend.mcp_servers.caldav import CalDAVServer
            caldav = CalDAVServer(url=caldav_url, username=caldav_user, password=caldav_pw)
        except Exception as e:
            logging.getLogger(__name__).warning("CalDAVServer init failed: %r", e)

    bocha_key = os.environ.get("BOCHA_API_KEY")
    if bocha_key:
        try:
            from backend.mcp_servers.bocha_search import BochaSearchServer
            bocha = BochaSearchServer(api_key=bocha_key)
        except Exception as e:
            logging.getLogger(__name__).warning("BochaSearchServer init failed: %r", e)

    from backend.mcp_servers.memory import MemoryServer
    memory = MemoryServer(store=memory_store)

    return ToolRegistry(
        bilibili=bilibili,
        pyncm=pyncm,
        memory=memory,
        caldav=caldav,
        bocha=bocha,
        browser=None,
        shell=None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-Persona Voice Agent CLI")
    parser.add_argument("--persona", default="assistant", help="Persona name (default: assistant)")
    parser.add_argument("--personas-dir", default="personas", help="Personas root directory")
    parser.add_argument("--no-tools", action="store_true", help="Disable tool calling")
    parser.add_argument("--voice", action="store_true", help="Enable voice mode (requires hardware)")
    parser.add_argument("--debug", action="store_true", help="Print every wake-window Whisper transcript")
    parser.add_argument("--wake-threshold", type=float, default=0.3,
                        help="Wake word confidence threshold 0–1 (default: 0.3, lower=more sensitive)")
    args = parser.parse_args()

    if args.debug:
        os.environ["WAKE_DEBUG"] = "1"
        logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
        logging.getLogger("edge.wakeword").setLevel(logging.DEBUG)

    persona_dir = Path(args.personas_dir) / args.persona
    if not persona_dir.is_dir():
        print(f"Persona not found: {persona_dir}")
        print("Available personas:")
        from core.persona import list_personas
        for name in list_personas(Path(args.personas_dir)):
            print(f"  - {name}")
        return

    persona = load_persona(persona_dir)
    print(f"Loaded persona: {persona.name}")
    print(f"  system_prompt: {persona.system_prompt[:80]}...")

    memory_store = MemoryStore("data/memory.db")
    tracer = Tracer("data/traces.db")
    guard = Guard()

    llm_call = create_llm_callable(role="default_fast")

    if args.no_tools:
        registry = None
        llm_call_with_tools = None
        print("  tools: disabled (--no-tools)")
    else:
        registry = _build_tool_registry(memory_store)
        visible = registry.filter_for_persona(persona, speaker_verified=False)
        print(f"  tools available: {len(visible)} / {len(registry.list_specs())} (speaker_verified=False)")
        for spec in visible:
            marker = "✎" if spec.is_write else " "
            print(f"    {marker} {spec.name}  [{spec.risk}]")
        llm_call_with_tools = create_llm_callable_with_tools(role="default_fast")

    graph = build_main_graph(
        llm_call,
        security_guard=guard,
        tool_registry=registry,
        persona=persona,
        speaker_verified=False,
        llm_call_with_tools=llm_call_with_tools,
        system_prompt=persona.system_prompt,
    )

    print(f"\n{'='*50}")
    if args.voice:
        print(f"  {persona.name} — 语音模式")
        print(f"  呼唤「{persona.wake_word or persona.name}」开始对话")
    else:
        print(f"  {persona.name} — 文字对话模式")
        print(f"  输入消息开始对话，/quit 退出")
    print(f"{'='*50}\n")

    if args.voice:
        os.environ.setdefault("WAKE_THRESHOLD", str(args.wake_threshold))

    try:
        if args.voice:
            asyncio.run(_voice_loop(graph, persona, tracer, memory_store))
        else:
            asyncio.run(_chat_loop(graph, persona, tracer))
    except KeyboardInterrupt:
        print("\n再见！")


# ---------------------------------------------------------------------------
# Text chat loop
# ---------------------------------------------------------------------------

async def _chat_loop(graph, persona, tracer: Tracer) -> None:
    """Interactive text chat loop."""
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input.lower() in ("/quit", "/exit", "/q"):
            print("再见！")
            break

        trace_id = str(uuid.uuid4())[:12]
        tracer.trace_add(
            trace_id=trace_id,
            persona=persona.name,
            user_id="owner",
            session_id="owner",
            role="chat",
            input_messages_count=1,
        )
        try:
            state = await run_graph(
                graph,
                input_text=user_input,
                persona=persona.name,
                user_id="owner",
                trace_id=trace_id,
            )
        except Exception as e:
            tracer.trace_set_error(trace_id, f"{type(e).__name__}: {e}")
            print(f"\n[error] {e}\n")
            continue

        response = state.get("final_response", "")
        tools_called = state.get("tools_called") or []

        print(f"\n{persona.name}: {response}")
        if tools_called:
            print(f"  [tools: {', '.join(tools_called)}]")
        print(f"  [{trace_id}]\n")


# ---------------------------------------------------------------------------
# Voice loop
# ---------------------------------------------------------------------------

async def _voice_loop(graph, persona, tracer: Tracer, memory_store: MemoryStore) -> None:
    """Full voice conversation loop: wake word → STT → LLM → TTS → play.

    Also runs proactive scan as a background task every 5 minutes.
    Requires: sounddevice, faster-whisper, edge-tts (+ miniaudio for playback).
    Falls back gracefully when hardware packages are not installed.
    """
    _check_voice_deps()

    from edge.audio_capture import stream_microphone, read_until_silence
    from edge.wakeword import WakeWordListener
    from backend.tts import play_audio_mp3
    from backend.tts.edge_tts_client import EdgeTTSClient
    from backend.streaming.pipeline import _transcribe

    tts_client = EdgeTTSClient(voice=persona.voice)
    wake_word = persona.wake_word or persona.name
    threshold = float(os.environ.get("WAKE_THRESHOLD", "0.3"))
    listener = WakeWordListener(persona=wake_word, threshold=threshold)
    if os.environ.get("WAKE_DEBUG") == "1":
        print(f"[语音] DEBUG 模式：threshold={threshold:.2f}，每个滑窗 transcript 都会打印")

    # Lock ensures proactive TTS never overlaps with a conversation turn
    _turn_lock = asyncio.Lock()

    # Show which audio output device will be used
    _log_output_device()

    print(f"[语音] 正在加载 Whisper 模型（首次启动稍慢）...")
    await listener.load_model()
    print(f"[语音] 就绪。呼唤「{wake_word}」开始对话。Ctrl+C 退出。\n")

    proactive_task = asyncio.create_task(
        _proactive_task(memory_store, persona.name, tts_client, play_audio_mp3, _turn_lock)
    )

    # ONE microphone stream serves both wake detection and post-wake capture.
    # Opening a second InputStream on the same device fails on Windows
    # (PaErrorCode -9996), so we read the user's speech from this same stream.
    mic_stream = stream_microphone()

    try:
        async for persona_name, confidence in listener.listen(mic_stream):
            print(f"\n[唤醒] {persona_name} (置信度 {confidence:.0%})")
            print("[录音中...] 请说话（停顿 1.5 秒自动结束）")

            async with _turn_lock:
                t_turn = time.monotonic()

                # ── Capture (reads from the shared mic stream) ─────────────
                try:
                    audio_arr = await read_until_silence(
                        mic_stream,
                        silence_threshold=0.015,
                        silence_duration=1.5,
                        max_duration=10.0,
                    )
                except RuntimeError as exc:
                    print(f"[麦克风错误] {exc}")
                    continue

                if audio_arr is None or len(audio_arr) == 0:
                    print("[无声音] 跳过")
                    continue
                t_capture_ms = int((time.monotonic() - t_turn) * 1000)

                # ── STT ────────────────────────────────────────────────────
                t0 = time.monotonic()
                transcript = await _transcribe(audio_arr)
                t_stt_ms = int((time.monotonic() - t0) * 1000)

                if not transcript.strip():
                    print("[识别为空] 跳过")
                    continue
                print(f"[识别 {t_stt_ms}ms] {transcript}")

                # ── LLM ────────────────────────────────────────────────────
                trace_id = str(uuid.uuid4())[:12]
                tracer.trace_add(
                    trace_id=trace_id,
                    persona=persona.name,
                    user_id="owner",
                    session_id="owner",
                    role="voice",
                    input_messages_count=1,
                )
                span_llm = f"{trace_id}_llm"
                tracer.span_add(span_llm, trace_id, "llm_call")
                t0 = time.monotonic()
                try:
                    state = await run_graph(
                        graph,
                        input_text=transcript,
                        persona=persona.name,
                        user_id="owner",
                        trace_id=trace_id,
                    )
                except Exception as exc:
                    t_llm_ms = int((time.monotonic() - t0) * 1000)
                    tracer.span_end(span_llm, t_llm_ms, error=str(exc))
                    tracer.trace_set_error(trace_id, str(exc))
                    print(f"[LLM 错误] {exc}")
                    continue
                t_llm_ms = int((time.monotonic() - t0) * 1000)
                tracer.span_end(span_llm, t_llm_ms)

                response = state.get("final_response", "")
                tools_called = state.get("tools_called") or []

                print(f"\n{persona.name}: {response}")
                if tools_called:
                    print(f"  [tools: {', '.join(tools_called)}]")

                # ── TTS + 播放 ─────────────────────────────────────────────
                t_tts_synth_ms = 0
                t_tts_play_ms = 0
                if response:
                    span_tts = f"{trace_id}_tts"
                    tracer.span_add(span_tts, trace_id, "tts_synth")
                    t0 = time.monotonic()
                    try:
                        mp3_bytes = await tts_client.synthesize(response)
                        t_tts_synth_ms = int((time.monotonic() - t0) * 1000)
                        tracer.span_end(span_tts, t_tts_synth_ms)

                        t1 = time.monotonic()
                        await play_audio_mp3(mp3_bytes)
                        t_tts_play_ms = int((time.monotonic() - t1) * 1000)
                    except Exception as exc:
                        t_tts_synth_ms = int((time.monotonic() - t0) * 1000)
                        tracer.span_end(span_tts, t_tts_synth_ms, error=str(exc))
                        print(f"[TTS 错误] {exc}")

                t_total_ms = int((time.monotonic() - t_turn) * 1000)
                print(
                    f"  [延迟 录音={t_capture_ms}ms "
                    f"STT={t_stt_ms}ms "
                    f"LLM={t_llm_ms}ms "
                    f"TTS合成={t_tts_synth_ms}ms "
                    f"播放={t_tts_play_ms}ms "
                    f"总={t_total_ms}ms]"
                )

            print(f"\n[等待唤醒「{wake_word}」...]\n")

    except KeyboardInterrupt:
        print("\n再见！")
    finally:
        proactive_task.cancel()
        try:
            await proactive_task
        except asyncio.CancelledError:
            pass


async def _proactive_task(
    memory_store: MemoryStore,
    persona_name: str,
    tts_client,
    play_fn,
    turn_lock: asyncio.Lock,
    interval: float = 300.0,
) -> None:
    """Background task: run proactive scanner every ``interval`` seconds.

    Speaks the highest-priority event if one is found, waiting for any active
    conversation turn to finish first (via ``turn_lock``).
    """
    from backend.proactive.scanner import proactive_scan

    log = logging.getLogger(__name__)
    while True:
        await asyncio.sleep(interval)
        try:
            events = await proactive_scan(memory_store, "owner", persona_name)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Proactive scan failed: %r", exc)
            continue

        if not events:
            continue

        top = events[0]
        print(f"\n[主动感知] {top.trigger}: {top.message}")
        async with turn_lock:
            try:
                mp3_bytes = await tts_client.synthesize(top.message)
                await play_fn(mp3_bytes)
            except Exception as exc:
                log.warning("Proactive TTS failed: %r", exc)


def _log_output_device() -> None:
    """Print the audio output device that will be used for TTS playback."""
    try:
        import sounddevice as sd
        from backend.tts import _find_output_device
        dev_id = _find_output_device()
        if dev_id is None:
            info = sd.query_devices(kind="output")
            name = info.get("name", "unknown") if isinstance(info, dict) else str(info)
            print(f"[音频输出] 使用 OS 默认设备：{name}")
            print(f"  提示：设置 $env:VOICE_OUTPUT_DEVICE='蓝牙音箱名' 切换输出设备")
        else:
            info = sd.query_devices(dev_id)
            name = info.get("name", str(dev_id)) if isinstance(info, dict) else str(info)
            print(f"[音频输出] 已选择设备 [{dev_id}]：{name}")
    except Exception:
        pass  # sounddevice not installed or query failed — non-fatal


def _check_voice_deps() -> None:
    """Print warnings for missing voice dependencies (non-fatal)."""
    missing = []
    for pkg, install in [
        ("sounddevice", "sounddevice"),
        ("faster_whisper", "faster-whisper"),
        ("edge_tts", "edge-tts"),
        ("miniaudio", "miniaudio"),
    ]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(install)

    if missing:
        print("[警告] 以下语音依赖未安装，部分功能降级：")
        print(f"  pip install {' '.join(missing)}")
        print()


if __name__ == "__main__":
    main()
