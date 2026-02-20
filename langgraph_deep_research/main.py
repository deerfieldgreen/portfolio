"""
LangGraph Deep Research Application.

This module implements a LangGraph-based workflow for conducting comprehensive
research using:
- Novita AI (Qwen 3.5 397B) for question generation
- Parallel AI Deep Research API for conducting research
- LangGraph for workflow orchestration
"""

import logging
import sys
from pathlib import Path
from typing import List, Dict, Optional, TypedDict, Any
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage

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
    3. synthesize_results: Combine findings into a final report
    """

    def __init__(self):
        """Initialize the research workflow."""
        Config.validate()
        
        self.question_generator = QuestionGenerator()
        self.research_client = ParallelResearchClient()
        
        # Build the workflow graph
        self.graph = self._build_graph()
        
        logger.info("ResearchWorkflow initialized")

    def _build_graph(self) -> StateGraph:
        """
        Build the LangGraph workflow.
        
        Returns:
            Compiled StateGraph ready for execution
        """
        # Create the graph
        workflow = StateGraph(ResearchState)
        
        # Add nodes
        workflow.add_node("generate_questions", self.generate_questions)
        workflow.add_node("conduct_research", self.conduct_research)
        workflow.add_node("synthesize_results", self.synthesize_results)
        
        # Define edges
        workflow.set_entry_point("generate_questions")
        workflow.add_edge("generate_questions", "conduct_research")
        workflow.add_edge("conduct_research", "synthesize_results")
        workflow.add_edge("synthesize_results", END)
        
        # Compile the graph
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
            # Provide fallback questions with improved grammar
            topic_lower = topic.lower()
            state["questions"] = [
                f"What are the key aspects of {topic_lower}?",
                f"What are recent developments in {topic_lower}?",
                f"What are the main challenges and opportunities in {topic_lower}?"
            ]
            logger.info(f"Using fallback questions")
        
        return state

    def conduct_research(self, state: ResearchState) -> ResearchState:
        """
        Node: Conduct research for each question.
        
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
        Node: Synthesize research results into a final report.
        
        Args:
            state: Current workflow state
            
        Returns:
            Updated state with final report
        """
        logger.info("Step 3: Synthesizing results into final report")
        state["step"] = "synthesize_results"
        
        try:
            report = self._create_report(
                state["topic"],
                state["questions"],
                state["research_results"]
            )
            state["final_report"] = report
            
            logger.info("Final report generated successfully")
            
        except Exception as e:
            logger.error(f"Error synthesizing results: {str(e)}")
            state["final_report"] = "Error generating report"
        
        return state

    def _create_report(
        self,
        topic: str,
        questions: List[str],
        results: List[Dict[str, Any]]
    ) -> str:
        """
        Create a formatted final report from research results.
        
        Args:
            topic: The research topic
            questions: List of research questions
            results: List of research result dictionaries
            
        Returns:
            Formatted report as a string
        """
        report_lines = []
        
        # Title and executive summary
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
        
        # Main findings
        report_lines.append("## Detailed Findings")
        report_lines.append("")
        
        for i, (question, result) in enumerate(zip(questions, results), 1):
            report_lines.append(f"### {i}. {question}")
            report_lines.append("")
            
            if result.get("status") == "completed" and result.get("answer"):
                report_lines.append(result["answer"])
                report_lines.append("")
                
                # Add citations
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
        
        # Conclusion
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
        Run the complete research workflow.
        
        Args:
            topic: The research topic/query
            
        Returns:
            Final state dictionary containing all results
        """
        logger.info(f"Starting research workflow for topic: {topic}")
        
        # Initialize state
        initial_state: ResearchState = {
            "topic": topic,
            "questions": [],
            "research_results": [],
            "final_report": None,
            "step": "initial"
        }
        
        # Execute the graph
        final_state = self.graph.invoke(initial_state)
        
        logger.info("Research workflow completed")
        return final_state


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
