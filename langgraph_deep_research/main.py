"""
LangGraph Deep Research Application.

This module implements a LangGraph-based workflow for conducting comprehensive
research using:
- Novita AI (Qwen 3.5 397B) for question generation and report synthesis
- Parallel AI Deep Research API for conducting research
- LangGraph for workflow orchestration
"""

import logging
import sys
from pathlib import Path
from typing import List, Dict, Optional, TypedDict, Any, Generator
from openai import OpenAI
from langgraph.graph import StateGraph, END

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from tools.question_generator import QuestionGenerator
from tools.parallel_research import ParallelResearchClient
from config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ResearchState(TypedDict):
    """
    State schema for the research workflow.

    Attributes:
        topic: The original research topic/query
        questions: Generated research questions
        research_results: Results from Parallel AI research
        final_report: Synthesized final report
        step: Current step in the workflow
    """
    topic: str
    questions: List[str]
    research_results: List[Dict[str, Any]]
    final_report: Optional[str]
    step: str


class ResearchWorkflow:
    """
    LangGraph workflow for conducting deep research.

    The workflow consists of:
    1. generate_questions: Generate research questions from the topic
    2. conduct_research: Research each question using Parallel AI
    3. synthesize_results: Combine findings into a final report via LLM

    Use run() for a blocking call or stream() to receive token-level output
    from the synthesis step along with status updates throughout.
    """

    def __init__(self):
        """Initialize the research workflow."""
        Config.validate()
        novita_config = Config.get_novita_config()

        self.question_generator = QuestionGenerator()
        self.research_client = ParallelResearchClient()

        # LLM client for report synthesis
        self.synthesis_client = OpenAI(
            api_key=novita_config["api_key"],
            base_url=novita_config["base_url"]
        )
        self.synthesis_model = novita_config["model"]
        self.synthesis_temperature = novita_config["temperature"]
        self.synthesis_max_tokens = novita_config["synthesis_max_tokens"]

        # Build the workflow graph
        self.graph = self._build_graph()

        logger.info("ResearchWorkflow initialized")

    def _build_graph(self):
        """
        Build the LangGraph workflow.

        Returns:
            Compiled StateGraph ready for execution
        """
        workflow = StateGraph(ResearchState)

        workflow.add_node("generate_questions", self.generate_questions)
        workflow.add_node("conduct_research", self.conduct_research)
        workflow.add_node("synthesize_results", self.synthesize_results)

        workflow.set_entry_point("generate_questions")
        workflow.add_edge("generate_questions", "conduct_research")
        workflow.add_edge("conduct_research", "synthesize_results")
        workflow.add_edge("synthesize_results", END)

        return workflow.compile()

    def generate_questions(self, state: ResearchState) -> ResearchState:
        """
        Node: Generate research questions from the topic.

        Args:
            state: Current workflow state

        Returns:
            Updated state with generated questions
        """
        logger.info(f"Step 1: Generating questions for topic: {state['topic']}")
        state["step"] = "generate_questions"

        try:
            questions = self.question_generator.generate_questions(state["topic"])
            state["questions"] = questions

            logger.info(f"Generated {len(questions)} questions:")
            for i, q in enumerate(questions, 1):
                logger.info(f"  {i}. {q}")

        except Exception as e:
            logger.error(f"Error generating questions: {str(e)}")
            topic_lower = state["topic"].lower()
            state["questions"] = [
                f"What are the key aspects of {topic_lower}?",
                f"What are recent developments in {topic_lower}?",
                f"What are the main challenges and opportunities in {topic_lower}?"
            ]
            logger.info("Using fallback questions")

        return state

    def conduct_research(self, state: ResearchState) -> ResearchState:
        """
        Node: Conduct research for each question in parallel.

        Args:
            state: Current workflow state

        Returns:
            Updated state with research results
        """
        logger.info(f"Step 2: Conducting research on {len(state['questions'])} questions")
        state["step"] = "conduct_research"

        try:
            results = self.research_client.research_multiple(state["questions"])
            state["research_results"] = results

            logger.info(f"Completed research for {len(results)} questions")

        except Exception as e:
            logger.error(f"Error conducting research: {str(e)}")
            state["research_results"] = []

        return state

    def synthesize_results(self, state: ResearchState) -> ResearchState:
        """
        Node: Synthesize research results into a final report via LLM.

        Calls the Novita AI model and collects the full streamed response.
        Falls back to the template-based report if the LLM call fails.

        Args:
            state: Current workflow state

        Returns:
            Updated state with final report
        """
        logger.info("Step 3: Synthesizing results into final report")
        state["step"] = "synthesize_results"

        try:
            tokens = list(
                self._stream_synthesis(
                    state["topic"],
                    state["questions"],
                    state["research_results"]
                )
            )
            state["final_report"] = "".join(tokens)
            logger.info("Final report generated successfully")

        except Exception as e:
            logger.error(f"LLM synthesis failed, falling back to template: {str(e)}")
            try:
                state["final_report"] = self._create_report(
                    state["topic"],
                    state["questions"],
                    state["research_results"]
                )
            except Exception as fallback_error:
                logger.error(f"Template fallback also failed: {str(fallback_error)}")
                state["final_report"] = "Error generating report"

        return state

    def _stream_synthesis(
        self,
        topic: str,
        questions: List[str],
        results: List[Dict[str, Any]]
    ) -> Generator[str, None, None]:
        """
        Stream synthesis tokens from the Novita AI LLM.

        Args:
            topic: The research topic
            questions: List of research questions
            results: List of research result dictionaries

        Yields:
            Text tokens from the LLM as they arrive
        """
        prompt = self._build_synthesis_prompt(topic, questions, results)

        stream = self.synthesis_client.chat.completions.create(
            model=self.synthesis_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert research analyst. Synthesize research "
                        "findings into clear, well-structured Markdown reports."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=self.synthesis_temperature,
            max_tokens=self.synthesis_max_tokens,
            stream=True,
        )

        for chunk in stream:
            if not chunk.choices:   # final [DONE] chunk has an empty choices list
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def _build_synthesis_prompt(
        self,
        topic: str,
        questions: List[str],
        results: List[Dict[str, Any]]
    ) -> str:
        """Build the synthesis prompt from research questions and results."""
        findings_parts = []
        for i, (question, result) in enumerate(zip(questions, results), 1):
            if result.get("status") == "completed" and result.get("answer"):
                citations = result.get("citations", [])
                citation_text = ""
                if citations:
                    lines = [
                        f"  - [{c.get('title', 'Source')}]({c.get('url', '')})"
                        if c.get("url")
                        else f"  - {c.get('title', 'Source')}"
                        for c in citations
                    ]
                    citation_text = "\n**Sources:**\n" + "\n".join(lines)
                findings_parts.append(
                    f"**Question {i}: {question}**\n{result['answer']}{citation_text}"
                )
            else:
                error = result.get("error", "unknown error")
                findings_parts.append(
                    f"**Question {i}: {question}**\n*Research unavailable: {error}*"
                )

        findings = "\n\n".join(findings_parts)

        return (
            f'Based on the following research findings about "{topic}", '
            f"write a comprehensive research report.\n\n"
            f"## Research Findings\n\n{findings}\n\n"
            f"Write a well-structured Markdown report with these sections:\n"
            f"1. `# Research Report: {topic}` — the document title\n"
            f"2. `## Executive Summary` — a concise 2-3 sentence overview\n"
            f"3. `## Detailed Findings` — one `###` subsection per question "
            f"with key insights; preserve source citations inline\n"
            f"4. `## Conclusion` — synthesized takeaways across all findings\n\n"
            f"Be thorough but concise. Use Markdown formatting throughout."
        )

    def _create_report(
        self,
        topic: str,
        questions: List[str],
        results: List[Dict[str, Any]]
    ) -> str:
        """
        Fallback: create a formatted report from research results using templates.

        Args:
            topic: The research topic
            questions: List of research questions
            results: List of research result dictionaries

        Returns:
            Formatted report as a string
        """
        report_lines = []

        report_lines.append(f"# Research Report: {topic}")
        report_lines.append("")
        report_lines.append("## Executive Summary")
        report_lines.append("")
        report_lines.append(
            f"This report presents comprehensive research on '{topic}', "
            f"addressing {len(questions)} key research questions through "
            f"in-depth investigation."
        )
        report_lines.append("")

        report_lines.append("## Detailed Findings")
        report_lines.append("")

        for i, (question, result) in enumerate(zip(questions, results), 1):
            report_lines.append(f"### {i}. {question}")
            report_lines.append("")

            if result.get("status") == "completed" and result.get("answer"):
                report_lines.append(result["answer"])
                report_lines.append("")

                citations = result.get("citations", [])
                if citations:
                    report_lines.append("**Sources:**")
                    for j, citation in enumerate(citations, 1):
                        title = citation.get("title", "Unknown")
                        url = citation.get("url", "")
                        if url:
                            report_lines.append(f"{j}. [{title}]({url})")
                        else:
                            report_lines.append(f"{j}. {title}")
                    report_lines.append("")
            else:
                error_msg = result.get("error", "Research unavailable")
                report_lines.append(f"*Research could not be completed: {error_msg}*")
                report_lines.append("")

        report_lines.append("## Conclusion")
        report_lines.append("")

        successful_results = [r for r in results if r.get("status") == "completed"]
        report_lines.append(
            f"This research covered {len(questions)} questions, with "
            f"{len(successful_results)} successfully completed. The findings provide "
            f"a comprehensive overview of {topic} from multiple perspectives."
        )
        report_lines.append("")

        return "\n".join(report_lines)

    def run(self, topic: str) -> Dict[str, Any]:
        """
        Run the complete research workflow (blocking).

        Args:
            topic: The research topic/query

        Returns:
            Final state dictionary containing all results
        """
        logger.info(f"Starting research workflow for topic: {topic}")

        initial_state: ResearchState = {
            "topic": topic,
            "questions": [],
            "research_results": [],
            "final_report": None,
            "step": "initial"
        }

        final_state = self.graph.invoke(initial_state)

        logger.info("Research workflow completed")
        return final_state

    def _mock_research_results(self, questions: List[str]) -> List[Dict[str, Any]]:
        """
        Return instant stub results for every question.

        Used with ``mock=True`` to skip Parallel AI during fast iteration.
        Question generation and LLM synthesis still use the real APIs so the
        full streaming pipeline is exercised without the 10-30 minute wait.

        Args:
            questions: The generated research questions

        Returns:
            List of stub result dicts that look like real Parallel AI output
        """
        return [
            {
                "question": q,
                "answer": (
                    f"[MOCK ANSWER] Placeholder research findings for: '{q}'. "
                    "In production this would contain comprehensive analysis from "
                    "Parallel AI's deep research pipeline."
                ),
                "citations": [
                    {"title": "Mock Source A", "url": "https://example.com/a"},
                    {"title": "Mock Source B", "url": "https://example.com/b"},
                ],
                "status": "completed",
            }
            for q in questions
        ]

    def stream(
        self, topic: str, mock: bool = False
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Run the research workflow with streaming output.

        Yields status events during question generation and research, then
        streams LLM synthesis tokens for the final report as they arrive.

        Each yielded dict has a ``type`` key with one of:
        - ``"status"``: a progress update; includes a ``"message"`` string and
          optionally a ``"questions"`` list (after generation completes).
        - ``"token"``: a synthesis token; includes a ``"content"`` string.
        - ``"complete"``: final event; includes the full ``"state"`` dict.

        Args:
            topic: The research topic/query
            mock: If True, skip Parallel AI and use instant stub results.
                  Question generation and LLM synthesis still hit real APIs.
                  Useful for fast iteration and testing the streaming pipeline.

        Yields:
            Event dicts describing workflow progress and synthesis tokens.

        Example::

            workflow = ResearchWorkflow()
            for event in workflow.stream("quantum computing"):
                if event["type"] == "token":
                    print(event["content"], end="", flush=True)
                elif event["type"] == "status":
                    print(f"\\n[{event['message']}]")
        """
        state: ResearchState = {
            "topic": topic,
            "questions": [],
            "research_results": [],
            "final_report": None,
            "step": "initial"
        }

        # Step 1: Generate questions (always real)
        yield {"type": "status", "message": "Generating research questions..."}
        state = self.generate_questions(state)
        yield {
            "type": "status",
            "message": f"Generated {len(state['questions'])} research questions",
            "questions": state["questions"],
        }

        # Step 2: Research — real or mock
        if mock:
            yield {"type": "status", "message": "Skipping Parallel AI (mock mode) ..."}
            state["research_results"] = self._mock_research_results(state["questions"])
            state["step"] = "conduct_research"
        else:
            yield {"type": "status", "message": "Conducting deep research..."}
            state = self.conduct_research(state)

        completed = sum(
            1 for r in state["research_results"] if r.get("status") == "completed"
        )
        yield {
            "type": "status",
            "message": f"Research complete — {completed}/{len(state['questions'])} questions answered",
        }

        # Step 3: Stream synthesis tokens (always real)
        yield {"type": "status", "message": "Synthesizing findings into report..."}
        state["step"] = "synthesize_results"

        full_report = []
        try:
            for token in self._stream_synthesis(
                state["topic"], state["questions"], state["research_results"]
            ):
                full_report.append(token)
                yield {"type": "token", "content": token}

            state["final_report"] = "".join(full_report)

        except Exception as e:
            logger.error(f"LLM synthesis failed during streaming, using template: {str(e)}")
            state["final_report"] = self._create_report(
                state["topic"], state["questions"], state["research_results"]
            )
            # Emit the fallback report as a single token so callers get output
            yield {"type": "token", "content": state["final_report"]}

        yield {"type": "complete", "state": dict(state)}


def create_workflow() -> ResearchWorkflow:
    """
    Factory function to create a research workflow.

    Returns:
        Initialized ResearchWorkflow instance
    """
    return ResearchWorkflow()


def run_research(topic: str) -> Dict[str, Any]:
    """
    Convenience function to run research on a topic.

    Args:
        topic: The research topic

    Returns:
        Final state with all results
    """
    workflow = create_workflow()
    return workflow.run(topic)


def main_cli() -> None:
    """CLI entry point: stream synthesis tokens live, print completed report."""
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "LangGraph Deep Research: generate questions, run Parallel AI research "
            "in parallel, then stream an LLM-synthesized report."
        )
    )
    parser.add_argument(
        "topic",
        nargs="?",
        default="renewable energy storage technologies",
        help="Research topic (default: %(default)s)",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Disable streaming; wait for the full report before printing.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help=(
            "Skip Parallel AI deep research and use instant stub answers. "
            "Question generation and LLM synthesis still use real APIs. "
            "Useful for fast iteration and testing the streaming pipeline."
        ),
    )
    args = parser.parse_args()

    workflow = create_workflow()

    if args.no_stream:
        result = workflow.run(args.topic)
        if result.get("final_report"):
            print(result["final_report"])
        return

    # Streaming mode (default)
    for event in workflow.stream(args.topic, mock=args.mock):
        if event["type"] == "status":
            print(f"\n[{event['message']}]", flush=True)
            if "questions" in event:
                for i, q in enumerate(event["questions"], 1):
                    print(f"  {i}. {q}", flush=True)
        elif event["type"] == "token":
            print(event["content"], end="", flush=True)
        elif event["type"] == "complete":
            state = event["state"]
            completed = sum(
                1 for r in state["research_results"] if r.get("status") == "completed"
            )
            print(
                f"\n\n[Done — {completed}/{len(state['research_results'])} questions answered, "
                f"{len(state.get('final_report', ''))} character report]",
                flush=True,
            )


if __name__ == "__main__":
    main_cli()
