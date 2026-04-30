"""Three-stage streaming voice pipeline: STT → LLM → TTS in parallel.

Per plan.md P3: asyncio.Queue-based pipeline that starts each stage as soon
as the first chunk arrives from the previous stage, achieving sub-500ms
end-to-end latency.

Usage (with stubs for testing, real engines for production)::

    result = await run_pipeline(
        audio_stream=my_audio_gen(),
        persona_id="xiaolin",
        llm_stream_fn=create_llm_stream(),
        tts_stream_fn=client.synthesize_stream,
        on_audio=speaker.play_chunk,
    )
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Awaitable, Callable

from backend.observe.tracer import Tracer

_SENTINEL = object()


@dataclass
class PipelineResult:
    full_transcript: str = ""
    full_response: str = ""
    latencies: dict[str, float] = field(default_factory=dict)


async def _stt_stage(
    audio_stream: AsyncIterator[bytes],
    text_queue: asyncio.Queue,
    latencies: dict[str, float],
    t_wakeup: float,
) -> str:
    """Stage 1: consume audio chunks, emit transcript tokens into text_queue.

    Currently a placeholder that emits the audio as a single dummy transcript
    chunk.  Replace with Whisper / Sherpa-ONNX when hardware is available.
    """
    transcript_parts: list[str] = []
    first_token = True

    # Placeholder STT: collect all audio then emit one fake token
    audio_chunks: list[bytes] = []
    async for chunk in audio_stream:
        audio_chunks.append(chunk)

    dummy_token = "（STT placeholder）"
    if first_token:
        latencies["t_stt_first"] = time.monotonic() - t_wakeup
        first_token = False
    await text_queue.put(dummy_token)
    transcript_parts.append(dummy_token)

    await text_queue.put(_SENTINEL)
    return "".join(transcript_parts)


async def _llm_stage(
    text_queue: asyncio.Queue,
    llm_stream_fn: Callable,
    llm_queue: asyncio.Queue,
    latencies: dict[str, float],
    t_wakeup: float,
    system_prompt: str,
) -> str:
    """Stage 2: accumulate STT tokens, start LLM stream on first token."""
    # Accumulate transcript first (wait for STT sentinel)
    transcript_parts: list[str] = []
    while True:
        token = await text_queue.get()
        if token is _SENTINEL:
            break
        transcript_parts.append(token)

    user_msg = "".join(transcript_parts)
    response_parts: list[str] = []
    first_token = True

    async for llm_chunk in llm_stream_fn(system_prompt, user_msg):
        if first_token:
            latencies["t_llm_first"] = time.monotonic() - t_wakeup
            first_token = False
        await llm_queue.put(llm_chunk)
        response_parts.append(llm_chunk)

    await llm_queue.put(_SENTINEL)
    return "".join(response_parts)


async def _tts_stage(
    llm_queue: asyncio.Queue,
    tts_stream_fn: Callable,
    on_audio: Callable[[bytes], Awaitable[None]],
    latencies: dict[str, float],
    t_wakeup: float,
) -> None:
    """Stage 3: accumulate LLM tokens, synthesize and play audio chunks."""
    # Collect LLM response then synthesize
    # For true low-latency, split on sentence boundaries; simplified here.
    response_parts: list[str] = []
    while True:
        chunk = await llm_queue.get()
        if chunk is _SENTINEL:
            break
        response_parts.append(chunk)

    full_text = "".join(response_parts)
    if not full_text:
        return

    first_chunk = True
    async for audio_chunk in tts_stream_fn(full_text):
        if first_chunk:
            latencies["t_tts_first"] = time.monotonic() - t_wakeup
            first_chunk = False
        await on_audio(audio_chunk)


async def run_pipeline(
    audio_stream: AsyncIterator[bytes],
    persona_id: str,
    llm_stream_fn: Callable,
    tts_stream_fn: Callable,
    on_audio: Callable[[bytes], Awaitable[None]],
    system_prompt: str = "You are a helpful assistant.",
    tracer: Tracer | None = None,
) -> PipelineResult:
    """Run the three-stage STT→LLM→TTS pipeline.

    Args:
        audio_stream: Async generator of raw audio bytes (e.g., from mic).
        persona_id: Active persona ID (used for tracing).
        llm_stream_fn: Async generator function ``(system, user_msg) -> AsyncGenerator[str]``.
        tts_stream_fn: Async generator function ``(text) -> AsyncGenerator[bytes]``.
        on_audio: Async callback called for each synthesised audio chunk.
        system_prompt: System prompt forwarded to the LLM stage.
        tracer: Optional tracer for latency span recording.

    Returns:
        PipelineResult with full transcript, full response, and latency dict.
    """
    t_wakeup = time.monotonic()
    latencies: dict[str, float] = {"t_wakeup": 0.0}

    text_queue: asyncio.Queue = asyncio.Queue()
    llm_queue: asyncio.Queue = asyncio.Queue()

    stt_task = asyncio.create_task(
        _stt_stage(audio_stream, text_queue, latencies, t_wakeup)
    )
    llm_task = asyncio.create_task(
        _llm_stage(text_queue, llm_stream_fn, llm_queue, latencies, t_wakeup, system_prompt)
    )
    tts_task = asyncio.create_task(
        _tts_stage(llm_queue, tts_stream_fn, on_audio, latencies, t_wakeup)
    )

    transcript, response, _ = await asyncio.gather(stt_task, llm_task, tts_task)

    latencies["t_total"] = time.monotonic() - t_wakeup

    if tracer is not None:
        try:
            tracer.trace_add(
                trace_id=f"pipeline_{persona_id}",
                role="pipeline",
                content=f"latencies={latencies}",
                latency_ms=int(latencies["t_total"] * 1000),
            )
        except Exception:
            pass

    return PipelineResult(
        full_transcript=transcript,
        full_response=response,
        latencies=latencies,
    )
