"""
Parallel Research Client for Deep Research API.

This module provides a wrapper around the Parallel AI SDK for conducting
comprehensive research using their Deep Research API.
"""

import logging
import time
from typing import Dict, List, Optional, Any
from parallel import Parallel

from ..config import Config

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
            # Submit the deep research task
            task = self.client.deep_research.submit(
                query=question,
                processor=self.processor_type
            )
            
            task_id = task.id
            logger.info(f"Task submitted with ID: {task_id}")
            
            # Poll for completion
            result = self._poll_for_completion(task_id, timeout)
            
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

    def _poll_for_completion(self, task_id: str, timeout: int) -> Any:
        """
        Poll the API until the task is complete or timeout is reached.
        
        Args:
            task_id: The task ID to poll
            timeout: Maximum time to wait in seconds
            
        Returns:
            The completed task result
            
        Raises:
            TimeoutError: If timeout is exceeded
        """
        start_time = time.time()
        
        while True:
            elapsed = time.time() - start_time
            
            if elapsed > timeout:
                raise TimeoutError(
                    f"Research task {task_id} did not complete within {timeout} seconds"
                )
            
            # Check task status
            task = self.client.deep_research.get(task_id)
            
            status = getattr(task, 'status', None)
            logger.debug(f"Task {task_id} status: {status}")
            
            if status == "completed":
                logger.info(f"Task {task_id} completed successfully")
                return task
            elif status == "failed":
                error_msg = getattr(task, 'error', 'Unknown error')
                raise Exception(f"Task {task_id} failed: {error_msg}")
            
            # Wait before next poll
            time.sleep(self.poll_interval)

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
        if hasattr(task_result, 'report'):
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
