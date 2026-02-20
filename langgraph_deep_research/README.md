# 🔬 LangGraph Deep Research

> **Agentic research at production quality.** Drop in a topic, get back a fully cited, LLM-synthesised research report — streamed token-by-token in real time.

Built on **LangGraph** for stateful orchestration, **Parallel AI Deep Research** for comprehensive multi-source investigation, and **Novita AI (Qwen 3.5 397B)** for razor-sharp question generation and live streaming synthesis.

---

## ✨ What It Does

```
You: "impact of AI on financial markets"

  ↓ Qwen 3.5 397B generates 5 targeted research questions (~30 s)

  ↓ 5 Parallel AI ultra-processor tasks fire simultaneously (~20 min)
    • HFT algorithms and market volatility
    • NLP sentiment analysis and price discovery
    • Homogeneous AI models and flash-crash risk
    • ML credit scoring vs. logistic regression
    • Regulatory frameworks for black-box AI

  ↓ Qwen 3.5 397B synthesises a structured report — streamed live

You: A fully cited, multi-section research report with tables,
     event evidence, regulatory analysis, and a conclusion.
```

---

## 🏗️ Architecture

### Workflow Graph

```
START
  │
  ▼
┌─────────────────────┐
│  generate_questions │  Novita AI · Qwen 3.5 397B
│                     │  → 3–5 focused research questions
└──────────┬──────────┘
           │
  ▼
┌─────────────────────┐
│  conduct_research   │  Parallel AI · ultra processor
│                     │  → All questions fired simultaneously
│   [Q1]──[Q2]──[Q3] │    via ThreadPoolExecutor
│      [Q4]──[Q5]    │  → Results collected in original order
└──────────┬──────────┘
           │
  ▼
┌─────────────────────┐
│  synthesize_results │  Novita AI · Qwen 3.5 397B (stream=True)
│                     │  → LLM-written report, streamed live
└──────────┬──────────┘
           │
          END
```

### State Schema

```python
class ResearchState(TypedDict):
    topic: str                        # Original research topic
    questions: List[str]              # Generated research questions
    research_results: List[Dict]      # Parallel AI findings + citations
    final_report: Optional[str]       # LLM-synthesised markdown report
    step: str                         # Current workflow node
```

### Component Map

| Component | Technology | Responsibility |
|-----------|-----------|----------------|
| 🧠 **Question Generator** | Novita AI · Qwen 3.5 397B | Generates 3–5 sharp, non-overlapping research questions; strips `<think>` reasoning tokens before JSON parsing |
| 🔍 **Research Client** | Parallel AI · ultra | Submits all questions in parallel; collects findings and citations; preserves order |
| 🔀 **Orchestrator** | LangGraph | Manages `ResearchState`, node transitions, and error propagation |
| ✍️ **Synthesiser** | Novita AI · Qwen 3.5 397B (streaming) | Writes the final report live via `stream=True`; falls back to template on failure |

---

## ⚡ Streaming Design

The `stream()` method yields a sequence of typed events so any consumer (CLI, API, WebSocket) can handle progress updates and report tokens independently:

```python
for event in workflow.stream("your topic"):

    if event["type"] == "status":
        # Progress update — e.g. "Generated 5 research questions"
        print(f"\n[{event['message']}]")
        if "questions" in event:
            for q in event["questions"]:
                print(f"  • {q}")

    elif event["type"] == "token":
        # Live synthesis token — print without newline for streaming effect
        print(event["content"], end="", flush=True)

    elif event["type"] == "complete":
        # Final state dict with the full report
        state = event["state"]
```

**Event types:**

| `type` | Extra keys | When |
|--------|-----------|------|
| `"status"` | `message`, optionally `questions` | Progress milestones |
| `"token"` | `content` | Each synthesis token from the LLM |
| `"complete"` | `state` | After the full report is assembled |

---

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.11+
- [Parallel AI](https://parallel.ai) API key (ultra processor)
- [Novita AI](https://novita.ai) API key

### 2. Install

```bash
cd langgraph_deep_research
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
# add PARALLEL_API_KEY and NOVITA_API_KEY
```

Or use [Doppler](https://doppler.com) (recommended for teams):

```bash
doppler setup   # link to your Doppler project
doppler run -- python main.py "your topic"
```

---

## 🖥️ CLI Usage

```bash
# Stream a full report (default)
python main.py "impact of AI on financial markets"

# Fast iteration — skip Parallel AI, use stub answers (~90 seconds total)
python main.py --mock "impact of AI on financial markets"

# Blocking mode — wait silently, then print the completed report
python main.py --no-stream "impact of AI on financial markets"

# Built-in help
python main.py --help
```

### `--mock` mode for fast iteration

The `--mock` flag is the key to tight development cycles:

| | `--mock` | Full run |
|---|---|---|
| Question generation (Novita AI) | ✅ Real | ✅ Real |
| Parallel AI deep research | ⚡ Instant stubs | ✅ Real |
| LLM synthesis streaming (Novita AI) | ✅ Real | ✅ Real |
| **Total time** | **~90 seconds** | **~20–30 minutes** |

Use `--mock` to iterate on prompts, streaming behaviour, and report formatting without burning Parallel AI credits or waiting 20 minutes per cycle.

---

## 📦 Library Usage

### Streaming (recommended)

```python
from main import create_workflow

workflow = create_workflow()

for event in workflow.stream("quantum computing in cryptography"):
    if event["type"] == "token":
        print(event["content"], end="", flush=True)
    elif event["type"] == "status":
        print(f"\n[{event['message']}]")
```

### Blocking

```python
result = workflow.run("quantum computing in cryptography")
print(result["final_report"])
```

### Mock mode (fast iteration)

```python
for event in workflow.stream("quantum computing", mock=True):
    ...  # Same event types, Parallel AI replaced with instant stubs
```

### Individual tools

```python
from tools.question_generator import generate_research_questions
from tools.parallel_research import conduct_research_multiple

questions = generate_research_questions("AI ethics in healthcare")
results   = conduct_research_multiple(questions)   # runs in parallel
```

---

## 🧪 Testing

```bash
python test_workflow.py
```

All 5 tests run with mocked APIs — **no API keys required**:

| Test | What it checks |
|------|---------------|
| `test_question_generation` | Fallback questions, state mutation |
| `test_research_execution` | Parallel client, error recovery |
| `test_result_synthesis` | LLM synthesis with template fallback |
| `test_state_transitions` | Full graph traversal via `workflow.run()` |
| `test_output_formatting` | Markdown structure, citation links |

---

## ⚙️ Configuration Reference

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `PARALLEL_API_KEY` | ✅ | Parallel AI Deep Research key |
| `NOVITA_API_KEY` | ✅ | Novita AI key (Qwen 3.5 397B) |

### `config.py` tunables

```python
# Question generation
MIN_QUESTIONS = 3             # Lower bound on questions generated
MAX_QUESTIONS = 5             # Upper bound on questions generated

# Novita AI
NOVITA_TEMPERATURE       = 0.7   # Creativity (0.0 = deterministic)
NOVITA_MAX_TOKENS        = 2000  # Budget for question generation
NOVITA_SYNTHESIS_MAX_TOKENS = 8000  # Budget for report synthesis

# Parallel AI
PARALLEL_PROCESSOR_TYPE  = "ultra"  # Research quality tier
PARALLEL_TIMEOUT         = 300      # Per-task timeout (seconds)
```

> **Why separate token limits?** Question generation needs ~200–400 tokens. Report synthesis for 5 deeply researched questions easily exceeds 2 000 tokens — the original shared limit caused the last section to be cut off mid-sentence.

---

## 📁 Project Structure

```
langgraph_deep_research/
├── main.py                 # Workflow, streaming, CLI entry point
├── config.py               # API keys and tunables
├── example.py              # Runnable demo (streaming + blocking)
├── test_workflow.py        # Full test suite (no API keys needed)
├── requirements.txt        # Python dependencies
├── .env.example            # Environment template
└── tools/
    ├── question_generator.py   # Novita AI · question generation
    └── parallel_research.py    # Parallel AI · concurrent research
```

---

## 🔧 Known Behaviours

| Behaviour | Explanation |
|-----------|-------------|
| **408 timeouts from Parallel AI** | Expected. The SDK uses long-polling with a ~10-minute window. 408 means "still working" — the SDK retries automatically. |
| **`<think>` tag stripping** | Qwen 3.5 is a reasoning model that emits chain-of-thought before the JSON. The parser strips those blocks before extracting questions. |
| **Questions arrive out of order** | Research runs in parallel; `Completed question 3/5` may log before `2/5`. Results are always returned in original question order. |
| **LLM synthesis fallback** | If the Novita streaming call fails, the synthesiser falls back to a template-based report automatically. |

---

## 🛠️ Extending the Workflow

### Add a custom node

```python
def validate_research(state: ResearchState) -> ResearchState:
    """Flag low-confidence results before synthesis."""
    state["research_results"] = [
        r for r in state["research_results"]
        if r.get("status") == "completed"
    ]
    return state

workflow.add_node("validate", validate_research)
workflow.add_edge("conduct_research", "validate")
workflow.add_edge("validate", "synthesize_results")
```

### Add conditional routing

```python
def needs_more_research(state: ResearchState) -> str:
    completed = sum(1 for r in state["research_results"] if r.get("status") == "completed")
    return "conduct_research" if completed < 3 else "synthesize_results"

workflow.add_conditional_edges("conduct_research", needs_more_research)
```

### Swap the LLM

```python
# config.py
NOVITA_MODEL    = "meta-llama/llama-3.1-405b-instruct"
NOVITA_BASE_URL = "https://api.novita.ai/v3/openai"

# Or point at any OpenAI-compatible endpoint
NOVITA_BASE_URL = "https://api.openai.com/v1"
NOVITA_MODEL    = "gpt-4o"
```

---

## 📊 Performance & Cost

### Typical timing

| Stage | Time |
|-------|------|
| Question generation | 20–60 s |
| Deep research (5 × ultra, parallel) | 15–30 min |
| LLM synthesis (streaming) | 1–3 min |
| **Total** | **~20–35 min** |

With `--mock`: **~90 seconds**.

### Approximate cost (5 questions)

| Service | Cost |
|---------|------|
| Novita AI — question gen + synthesis | ~$0.01 |
| Parallel AI — 5 × ultra tasks | ~$0.50–$2.50 |
| **Total per run** | **~$0.51–$2.51** |

---

## 🔒 Security

- API keys loaded exclusively from environment variables — never hard-coded
- `.env` listed in `.gitignore`
- All inputs validated before API calls
- API errors logged but not surfaced to callers in raw form

---

## 📄 License

[Apache 2.0](../LICENSE)
