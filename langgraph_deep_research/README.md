# LangGraph Deep Research

A production-ready prototype demonstrating agentic research workflows using **LangGraph** for orchestration, **Parallel AI Deep Research API** for comprehensive research, and **Novita AI (Qwen 3.5 397B)** for intelligent question generation.

---

## Overview

This project showcases a stateful, multi-step research workflow that:

1. **Generates Research Questions**: Uses Novita AI's Qwen 3.5 397B model to create focused, complementary research questions from a topic
2. **Conducts Deep Research**: Leverages Parallel AI's ultra processor to research each question comprehensively
3. **Synthesizes Results**: Combines findings into a structured report with inline citations

The entire workflow is orchestrated through LangGraph's state management system, providing transparent progress tracking and error handling.

---

## Architecture

### State Management

The workflow uses a `ResearchState` TypedDict to track:

```python
class ResearchState(TypedDict):
    topic: str                          # Original research topic
    questions: List[str]                # Generated questions
    research_results: List[Dict]        # Research findings
    final_report: Optional[str]         # Synthesized report
    step: str                           # Current workflow step
```

### Workflow Graph

```
START
  ↓
generate_questions (Novita AI - Qwen 3.5 397B)
  ↓
conduct_research (Parallel AI Deep Research)
  ↓
synthesize_results (Report Generation)
  ↓
END
```

### Components

| Component | Technology | Role |
|-----------|-----------|------|
| **Question Generator** | Novita AI (Qwen 3.5 397B) | Generates 3-5 focused research questions from a topic |
| **Research Client** | Parallel AI Deep Research | Conducts comprehensive research with citations |
| **Workflow Orchestrator** | LangGraph | Manages state transitions and execution flow |
| **Result Synthesizer** | Python | Combines findings into structured markdown report |

---

## Setup

### 1. Prerequisites

- Python 3.11+
- API keys for:
  - Parallel AI Deep Research
  - Novita AI

### 2. Installation

```bash
# Clone the repository (if not already done)
cd langgraph_deep_research

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

Create a `.env` file (use `.env.example` as a template):

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

```
PARALLEL_API_KEY=your_actual_parallel_api_key
NOVITA_API_KEY=your_actual_novita_api_key
```

**Important**: Never commit `.env` to version control. It's already in `.gitignore`.

---

## Usage

### Run the Example

```bash
python example.py
```

This demonstrates research on "renewable energy storage technologies" and shows:
- Generated research questions
- Progress through each research step
- Final synthesized report with citations

### Use as a Library

```python
from main import create_workflow

# Create the workflow
workflow = create_workflow()

# Run research on any topic
result = workflow.run("quantum computing applications in cryptography")

# Access results
print(f"Questions: {result['questions']}")
print(f"Report: {result['final_report']}")
```

### Direct Tool Usage

You can also use individual tools:

```python
from tools.question_generator import generate_research_questions
from tools.parallel_research import conduct_research

# Generate questions
questions = generate_research_questions("artificial intelligence ethics")

# Research a specific question
result = conduct_research("What are the ethical implications of AI in healthcare?")
```

---

## Example Output

### Generated Questions

```
1. What are the current leading renewable energy storage technologies?
2. How do lithium-ion batteries compare to flow batteries and other solutions?
3. What are the emerging technologies in grid-scale energy storage?
4. What are the economic considerations for renewable energy storage deployment?
5. What are the environmental impacts of different storage technologies?
```

### Research Result Structure

```python
{
    "question": "What are the current leading renewable energy storage technologies?",
    "answer": "The leading renewable energy storage technologies include...",
    "citations": [
        {
            "title": "Energy Storage Technology Review 2024",
            "url": "https://example.com/article"
        }
    ],
    "status": "completed"
}
```

### Final Report

The synthesized report includes:
- **Title and Executive Summary**: Overview of the research scope
- **Detailed Findings**: Section for each research question with answers and citations
- **Conclusion**: Summary of coverage and key insights

---

## Configuration Options

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `PARALLEL_API_KEY` | Yes | API key for Parallel AI Deep Research |
| `NOVITA_API_KEY` | Yes | API key for Novita AI services |

### Research Parameters

Edit `config.py` to customize:

```python
# Question generation
MIN_QUESTIONS = 3          # Minimum questions to generate
MAX_QUESTIONS = 5          # Maximum questions to generate

# Novita AI settings
NOVITA_TEMPERATURE = 0.7   # Creativity (0.0-1.0)
NOVITA_MAX_TOKENS = 2000   # Max response length

# Parallel AI settings
PARALLEL_PROCESSOR_TYPE = "ultra"  # Research quality level
PARALLEL_TIMEOUT = 300     # Max time per research task (seconds)
PARALLEL_POLL_INTERVAL = 5 # How often to check for results
```

---

## Testing

### Run Test Suite

```bash
python test_workflow.py
```

This runs tests using mocked APIs to verify:
- Question generation logic
- Research execution flow
- Result synthesis
- State transitions
- Output formatting

Tests pass without requiring actual API keys.

---

## Project Structure

```
langgraph_deep_research/
├── main.py                      # Main workflow implementation
├── config.py                    # Configuration management
├── example.py                   # Runnable example
├── test_workflow.py            # Test suite
├── requirements.txt            # Python dependencies
├── .env.example               # Environment template
├── README.md                  # This file
└── tools/
    ├── __init__.py
    ├── question_generator.py  # Novita AI question generation
    └── parallel_research.py   # Parallel AI research client
```

---

## How It Works

### 1. Question Generation Node

The `generate_questions` node:
- Takes the research topic from state
- Sends it to Novita AI's Qwen 3.5 397B model with a specialized prompt
- Extracts and validates 3-5 focused questions
- Updates state with questions
- Has fallback logic if generation fails

**Prompt Engineering**: The system prompt instructs the model to:
- Analyze the topic comprehensively
- Generate specific, actionable questions
- Ensure questions are complementary (different aspects)
- Format as a clean JSON array

### 2. Research Execution Node

The `conduct_research` node:
- Takes questions from state
- Submits each to Parallel AI's Deep Research API
- Polls for completion (with timeout)
- Extracts answers and citations
- Updates state with structured results

**Research Quality**: Uses Parallel AI's "ultra" processor for:
- Comprehensive source analysis
- Fact verification
- High-quality citations
- Detailed findings

### 3. Result Synthesis Node

The `synthesize_results` node:
- Takes topic, questions, and research results from state
- Creates a structured markdown report with:
  - Executive summary
  - Detailed findings per question
  - Inline citations
  - Conclusion
- Updates state with final report

**Report Structure**: Follows academic standards with clear sections and source attribution.

---

## Extending the Workflow

### Add New Nodes

```python
def custom_node(state: ResearchState) -> ResearchState:
    """Your custom processing logic."""
    state["step"] = "custom"
    # Do something with state
    return state

# Add to workflow
workflow.add_node("custom_node", custom_node)
workflow.add_edge("conduct_research", "custom_node")
workflow.add_edge("custom_node", "synthesize_results")
```

### Add Conditional Routing

```python
def should_do_more_research(state: ResearchState) -> str:
    """Decide if more research is needed."""
    if len(state["research_results"]) < 3:
        return "generate_questions"
    return "synthesize_results"

workflow.add_conditional_edges(
    "conduct_research",
    should_do_more_research
)
```

### Use Different Models

Edit `config.py`:

```python
# Try different Novita models
NOVITA_MODEL = "meta-llama/llama-3.1-405b-instruct"

# Or use OpenAI directly
NOVITA_BASE_URL = "https://api.openai.com/v1"
NOVITA_MODEL = "gpt-4"
```

---

## Best Practices

### Prompt Engineering

1. **Be Specific**: "Generate questions about X" → "Generate 5 specific research questions covering technical, economic, and environmental aspects of X"

2. **Provide Context**: Include what makes a good question in your prompts

3. **Request Structure**: Ask for JSON or markdown to make parsing easier

### API Usage

1. **Rate Limiting**: Add delays between requests if you hit rate limits

2. **Error Handling**: Both tools include retry logic and graceful degradation

3. **Timeouts**: Adjust `PARALLEL_TIMEOUT` based on your research complexity

### Cost Management

1. **Question Count**: Fewer questions = lower costs (3-5 is optimal)

2. **Model Selection**: Qwen 3.5 397B is cost-effective; GPT-4 is more expensive

3. **Processor Type**: Parallel AI's "ultra" is highest quality but costs more than "standard"

---

## Troubleshooting

### "API key not found" Error

**Solution**: Ensure `.env` file exists and contains valid keys:

```bash
cat .env  # Should show your keys
```

### "Module not found" Error

**Solution**: Install dependencies:

```bash
pip install -r requirements.txt
```

### Questions Don't Parse Correctly

**Solution**: The question generator handles multiple formats. If issues persist:
- Check `NOVITA_TEMPERATURE` (lower = more consistent)
- Verify the model is responding with JSON

### Research Times Out

**Solution**: Increase timeout in `config.py`:

```python
PARALLEL_TIMEOUT = 600  # 10 minutes
```

### Rate Limit Errors

**Solution**: Add delays between research tasks in `parallel_research.py`:

```python
import time
time.sleep(2)  # Wait 2 seconds between requests
```

---

## Performance Notes

### Typical Execution Times

- Question generation: 5-15 seconds
- Research per question: 30-120 seconds (depends on complexity)
- Synthesis: < 1 second

**Total for 5 questions**: 3-10 minutes

### API Costs (Approximate)

- Novita AI (Qwen 3.5 397B): ~$0.001 per question generation
- Parallel AI (Ultra processor): ~$0.10-0.50 per research task

**Total for 5 questions**: ~$0.50-2.50

---

## Security

- **No Secrets in Code**: All API keys come from environment variables
- **`.env` Not Committed**: Listed in `.gitignore`
- **Input Validation**: All user inputs are validated before API calls
- **Error Sanitization**: API errors don't leak sensitive information

---

## License

See [LICENSE](../LICENSE) in the parent directory (Apache 2.0).

---

## Support

For issues or questions:
1. Check this README's troubleshooting section
2. Review the code comments and docstrings
3. Open an issue in the repository

---

## Acknowledgments

- **LangGraph**: For stateful workflow orchestration
- **Parallel AI**: For comprehensive deep research capabilities
- **Novita AI**: For access to Qwen 3.5 397B and other models

---

## Future Enhancements

Potential additions to this prototype:
- [ ] Parallel question research (async execution)
- [ ] Interactive refinement (ask follow-up questions)
- [ ] Multi-format output (PDF, HTML, JSON)
- [ ] Research caching (avoid duplicate searches)
- [ ] Streaming results (show progress in real-time)
- [ ] Custom citation formatting (APA, MLA, Chicago)
- [ ] Source verification (fact-checking layer)
- [ ] Multi-language support
