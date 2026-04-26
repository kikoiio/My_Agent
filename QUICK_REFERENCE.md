# Quick Reference Guide

## Batch Overview (All Complete ✅)

| Batch | Module | Files | Status | Key Classes |
|-------|--------|-------|--------|-------------|
| 1 | Core Scaffolding | 17 | ✅ | Persona, CircuitBreaker, HAL |
| 2 | Memory+Observe+Security | 8 | ✅ | MemoryStore, DreamWorker, Tracer, Guard, RateLimiter |
| 3 | LLM Routing+Eval | 12 | ✅ | agent_loop, JudgeEnsemble, Calibrator, EvalHarness |
| 4 | TTS+MCP Servers | 11 | ✅ | CosyVoice, FishSpeech, Piper, 7 MCP servers |
| 5 | Pipecat+LangGraph | 3 | ✅ | PipecatPipeline, MainGraphState, PersonaGraphAdapter |
| 6 | Edge (Pi) Layer | 7 | ✅ | RPiHardware, RemoteHardware, FaceGate, VoicePrintGate |
| 7 | Scripts+Deploy | 9 | ✅ | 5 setup scripts, Docker, systemd, WireGuard |
| 8 | Tests+Docs | 14 | ✅ | 11 test cases, 2 probes, README, fixtures |
| **Total** | — | **88** | ✅ | — |

## File Structure

```
My_agent/
├── core/
│   ├── types.py              # Pydantic models
│   ├── persona.py            # Persona loading
│   ├── router.py             # Message routing
│   ├── breaker.py            # Circuit breaker
│   ├── loop.py               # Agent main loop ⭐
│   └── hardware/
│       ├── base.py           # HAL interface
│       ├── rpi.py            # RPi implementation
│       ├── remote.py         # WebSocket proxy
│       └── {null,mock}.py    # Test impls
├── backend/
│   ├── memory/
│   │   ├── store.py          # L1/L2/L3 SQLite ⭐
│   │   ├── dream.py          # Consolidation worker
│   │   ├── embedding_provider.py
│   │   └── mem0_plugin.py
│   ├── observe/
│   │   ├── tracer.py         # Distributed tracing ⭐
│   │   └── dashboard.py      # FastAPI HTML dashboard
│   ├── security/
│   │   ├── guard.py          # Injection detection ⭐
│   │   └── ratelimit.py      # Atomic rate limiting
│   ├── eval/
│   │   ├── judge_ensemble.py # 5-LLM jury ⭐
│   │   └── calibration.py    # Weight updates
│   ├── tts/
│   │   ├── cosyvoice_client.py
│   │   ├── fishspeech_client.py
│   │   └── piper_client.py
│   ├── mcp_servers/          # 7 MCP implementations
│   ├── nanobot/              # MCP registry
│   ├── orchestrator/
│   │   ├── graph.py          # LangGraph draft→critic→respond ⭐
│   │   └── persona_load.py   # Persona injection
│   ├── litellm/              # Router config template
│   └── pipecat_app.py        # Audio pipeline ⭐
├── edge/
│   ├── main.py               # Pi event loop ⭐
│   ├── wakeword.py           # Wake word listeners
│   ├── face_gate.py          # InsightFace verification
│   ├── voiceprint.py         # 3D-Speaker verification
│   └── audio_routing.py      # PipeWire+Bluetooth
├── eval/
│   ├── runners/
│   │   ├── harness.py        # Pytest entry point ⭐
│   │   ├── judge.py          # Single judge runner
│   │   └── reporter.py       # HTML report generator
│   ├── cases/                # Test cases by category
│   │   ├── core/
│   │   ├── security/
│   │   ├── persona/
│   │   ├── voice/
│   │   ├── tools/
│   │   ├── memory/
│   │   ├── social/
│   │   └── e2e_day/
│   ├── jury/
│   │   └── probes/           # Gold-standard calibration
│   └── fixtures/             # Mock hardware data
├── scripts/
│   ├── wakeword_train.py
│   ├── enroll_owner.py
│   ├── bilibili_qr_login.py
│   ├── ncm_qr_login.py
│   └── test_persona_voice.py
├── deploy/
│   ├── docker-compose.yml
│   ├── systemd/edge-runtime.service
│   ├── wireguard/setup.sh
│   └── check_hardware.sh
├── personas/
│   └── _template/            # 5-piece persona template
├── config.yaml
├── requirements.txt
├── README.md                 # Architecture + quick start
├── PROGRESS.md              # Batch status
└── IMPLEMENTATION_SUMMARY.md # Detailed summary
```

## Key Imports

```python
# Core
from core.types import Message, AgentState, ToolResult
from core.persona import Persona, load as load_persona
from core.loop import agent_loop, AgentLoopContext
from core.hardware import RPiHardware, RemoteHardware

# Memory
from backend.memory.store import MemoryStore
from backend.memory.dream import DreamWorker

# Observability
from backend.observe.tracer import Tracer
from backend.observe.dashboard import DashboardApp

# Security
from backend.security.guard import Guard, SecurityLevel
from backend.security.ratelimit import RateLimiter

# Evaluation
from backend.eval.judge_ensemble import JudgeEnsemble
from backend.eval.calibration import Calibrator
from eval.runners.harness import EvaluationHarness

# Audio
from backend.pipecat_app import PipecatPipeline
from backend.orchestrator.graph import build_main_graph

# Edge (Pi)
from edge.main import EdgeRuntime
from edge.wakeword import MultiWakeWordListener
from edge.face_gate import FaceGate
from edge.voiceprint import VoicePrintGate

# TTS
from backend.tts.cosyvoice_client import CosyVoiceClient
from backend.tts.fishspeech_client import FishSpeechClient
from backend.tts.piper_client import PiperClient
```

## Running Tests

```bash
# All tests
pytest eval/runners/harness.py -v

# Specific category
pytest eval/runners/harness.py -k "security" -v

# With coverage
pytest --cov=core eval/runners/harness.py

# Judge ensemble test
python -m eval.runners.judge --help
```

## Common Tasks

### Load a Persona
```python
from core.persona import load
persona = load("personas/kobe")
print(f"System prompt: {persona.system_prompt}")
print(f"Tools allowed: {persona.tools_allowed}")
```

### Initialize Memory
```python
from backend.memory.store import MemoryStore
store = MemoryStore("data/memory.db")
store.session_init("owner", "kobe")
episode_id = store.episode_add("owner", "kobe", "conversation", "User: Hi!")
```

### Start Dream Worker
```python
from backend.memory.dream import DreamWorker
worker = DreamWorker(store, llm_call_func)
await worker.consolidate("owner", "kobe")
```

### Initialize Tracer
```python
from backend.observe.tracer import Tracer
tracer = Tracer("data/trace.db")
tracer.trace_add("trace123", "kobe", "owner", "session1", "chat", 5)
```

### Security Guard
```python
from backend.security.guard import Guard
guard = Guard()
wrapped = guard.wrap_external("user input", "web_search")
print(f"Injection risk: {wrapped.injection_risk:.2%}")
```

### Evaluate with Jury
```python
from backend.eval.judge_ensemble import JudgeEnsemble
judges = [...]  # Judge instances
ensemble = JudgeEnsemble(judges)
verdict = await ensemble.evaluate("trace123", input_text, output_text)
print(f"Final score: {verdict.final_score:.2f}")
```

### Deploy to Pi
```bash
# 1. Check hardware
bash deploy/check_hardware.sh

# 2. Setup WireGuard
bash deploy/wireguard/setup.sh raspberrypi 192.168.1.100

# 3. Install systemd service
sudo cp deploy/systemd/edge-runtime.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable edge-runtime
sudo systemctl start edge-runtime

# 4. Enroll owner
python scripts/enroll_owner.py --owner-id owner

# 5. Train wake word
python scripts/wakeword_train.py kobe --samples 30
```

## API Schemas

### MemoryStore Methods
```python
store.session_init(user_id: str, persona: str) → None
store.episode_add(user_id: str, persona: str, event_type: str, content: str, metadata=None) → int
store.episode_search(user_id: str, persona: str, query: str, limit=10) → list[EpisodeEntry]
store.dream_add(user_id: str, persona: str, category: str, summary: str) → int
store.dream_list_recent(user_id: str, persona: str, limit=10) → list[DreamEntry]
```

### Tracer Methods
```python
tracer.trace_add(trace_id: str, persona: str, user_id: str, role: str) → None
tracer.span_add(span_id: str, trace_id: str, name: str) → None
tracer.event_add(event_id: str, span_id: str, event_type: str, metadata=None) → None
tracer.judge_add(trace_id: str, judge_id: str, score: float, verdict: str) → None
tracer.ratelimit_check(key: str, limit: int, window_start: float) → bool
```

### Guard Methods
```python
guard.wrap_external(content: str, source: str) → ExternalContent
guard.is_safe(wrapped: ExternalContent, threshold=0.5) → bool
guard.sanitize(text: str) → str
```

### agent_loop Signature
```python
async def agent_loop(
    ctx: AgentLoopContext,
    user_message: str,
    image_bytes: bytes | None = None,
) → tuple[str, AgentState, str]:
    """
    Execute single agent turn.
    Returns: (response_text, updated_state, trace_id)
    """
```

## Environment Variables

```bash
# LLM keys (backend/secrets/llm_keys.env)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...

# Biometric enrollment paths
FACE_ENROLLMENT_DIR=data/enrollments/faces
VOICE_ENROLLMENT_DIR=data/enrollments/voices

# WireGuard tunnel
WIREGUARD_PI_IP=10.0.0.2
WIREGUARD_BACKEND_IP=10.0.0.1

# Optional: Mem0 integration
MEM0_API_KEY=...
```

## Testing Checklist

- [ ] Import all modules: `python -c "from core import *; from backend import *"`
- [ ] Run harness: `pytest eval/runners/harness.py -v`
- [ ] Check hardware (Pi): `bash deploy/check_hardware.sh`
- [ ] Enroll owner: `python scripts/enroll_owner.py`
- [ ] Train wake word: `python scripts/wakeword_train.py kobe`
- [ ] Test TTS: `python scripts/test_persona_voice.py kobe`
- [ ] Start backend: `docker-compose up -d`
- [ ] Start edge: `systemctl start edge-runtime`

## Documentation Links

- **Architecture**: [plan.md](plan.md) §1-12
- **Implementation**: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
- **Progress**: [PROGRESS.md](PROGRESS.md)
- **Quick Start**: [README.md](README.md)
- **This Guide**: [QUICK_REFERENCE.md](QUICK_REFERENCE.md)

---

**Last Updated**: 2026-04-26  
**Status**: All 8 Batches Complete ✅
