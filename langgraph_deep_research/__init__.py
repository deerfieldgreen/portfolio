"""
LangGraph Deep Research - Agentic Research Workflow

A production-ready prototype for conducting comprehensive research using:
- LangGraph for workflow orchestration
- Parallel AI for deep research
- Novita AI (Qwen 3.5 397B) for question generation
"""

__version__ = "1.0.0"

from .main import create_workflow, run_research, ResearchWorkflow, ResearchState
from .tools.question_generator import QuestionGenerator, generate_research_questions
from .tools.parallel_research import ParallelResearchClient, conduct_research

__all__ = [
    "create_workflow",
    "run_research",
    "ResearchWorkflow",
    "ResearchState",
    "QuestionGenerator",
    "generate_research_questions",
    "ParallelResearchClient",
    "conduct_research",
]
