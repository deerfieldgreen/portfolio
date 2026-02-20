"""
Parallel Research Client for Deep Research API.

This module provides a wrapper around the Parallel AI SDK for conducting
comprehensive research using their Deep Research API.
"""

import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from parallel import Parallel

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config

logger = logging.getLogger(__name__)


class ParallelResearchClient:
    """
    Client wrapper for Parallel AI Deep Research API.
    
    This client handles:
    - Task submission to the Deep Research API
    - Polling for task completion
    - Result extraction with citations
    """

    def __init__(self):
        """Initialize the Parallel Research Client."""
        Config.validate()
        parallel_config = Config.get_parallel_config()
        
        self.client = Parallel(api_key=parallel_config["api_key"])
        self.processor_type = parallel_config["processor_type"]
        self.timeout = parallel_config["timeout"]
        self.poll_interval = parallel_config["poll_interval"]
        
        logger.info(f"Initialized ParallelResearchClient with processor: {self.processor_type}")

    def research(self, question: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """
        Submit a research question and wait for results.
        
        Args:
            question: The research question to investigate
            timeout: Optional timeout in seconds (default: from config)
            
        Returns:
            Dictionary containing:
                - question: The original question
                - answer: The research findings
                - citations: List of sources used
                - status: Completion status
                
        Raises:
            TimeoutError: If research takes longer than timeout
            Exception: If API call fails
        """
        if not question or not question.strip():
            raise ValueError("Question cannot be empty")
        
        timeout = timeout or self.timeout
        logger.info(f"Starting research for question: {question}")
        
        try:
            # Submit the deep research task using task_run.execute
            result = self.client.task_run.execute(
                input=question,
                output="Detailed research report with comprehensive analysis and citations.",
                processor=self.processor_type
            )
            
            logger.info(f"Research completed successfully")
            
            # Extract and structure the result
            return self._format_result(question, result)
            
        except Exception as e:
            logger.error(f"Error during research: {str(e)}")
            raise

    def research_multiple(self, questions: List[str]) -> List[Dict[str, Any]]:
        """
        Research multiple questions sequentially.
        
        Args:
            questions: List of research questions
            
        Returns:
            List of research result dictionaries
        """
        results = []
        
        for i, question in enumerate(questions, 1):
            logger.info(f"Researching question {i}/{len(questions)}")
            try:
                result = self.research(question)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to research question {i}: {str(e)}")
                # Add error result but continue with other questions
                results.append({
                    "question": question,
                    "answer": None,
                    "citations": [],
                    "status": "error",
                    "error": str(e)
                })
        
        return results

    def _format_result(self, question: str, task_result: Any) -> Dict[str, Any]:
        """
        Format the API result into a structured dictionary.
        
        Args:
            question: The original question
            task_result: The raw task result from the API
            
        Returns:
            Formatted result dictionary
        """
        result = {
            "question": question,
            "status": "completed"
        }
        
        # Extract answer/report
        if hasattr(task_result, 'output'):
            result["answer"] = task_result.output
        elif hasattr(task_result, 'report'):
            result["answer"] = task_result.report
        elif hasattr(task_result, 'result'):
            result["answer"] = task_result.result
        else:
            result["answer"] = str(task_result)
        
        # Extract citations/sources
        citations = []
        if hasattr(task_result, 'citations'):
            citations = task_result.citations
        elif hasattr(task_result, 'sources'):
            citations = task_result.sources
        elif hasattr(task_result, 'references'):
            citations = task_result.references
        
        result["citations"] = self._format_citations(citations)
        
        # Extract metadata
        if hasattr(task_result, 'metadata'):
            result["metadata"] = task_result.metadata
        
        return result

    def _format_citations(self, citations: Any) -> List[Dict[str, str]]:
        """
        Format citations into a consistent structure.
        
        Args:
            citations: Raw citations from the API
            
        Returns:
            List of citation dictionaries with 'title' and 'url' keys
        """
        if not citations:
            return []
        
        formatted = []
        
        if isinstance(citations, list):
            for citation in citations:
                if isinstance(citation, dict):
                    formatted.append({
                        "title": citation.get("title", citation.get("name", "Unknown")),
                        "url": citation.get("url", citation.get("link", "")),
                    })
                elif isinstance(citation, str):
                    formatted.append({
                        "title": citation,
                        "url": ""
                    })
        
        return formatted


def conduct_research(question: str) -> Dict[str, Any]:
    """
    Convenience function to conduct research on a single question.
    
    Args:
        question: The research question
        
    Returns:
        Research result dictionary
    """
    client = ParallelResearchClient()
    return client.research(question)


def conduct_research_multiple(questions: List[str]) -> List[Dict[str, Any]]:
    """
    Convenience function to conduct research on multiple questions.
    
    Args:
        questions: List of research questions
        
    Returns:
        List of research result dictionaries
    """
    client = ParallelResearchClient()
    return client.research_multiple(questions)
