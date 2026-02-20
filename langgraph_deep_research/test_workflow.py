"""
Test workflow for LangGraph Deep Research.

This script tests the workflow components without making actual API calls
by mocking the external services.
"""

import logging
import os
import sys
from typing import List, Dict, Any
from unittest.mock import Mock, patch, MagicMock

# Set dummy environment variables BEFORE importing modules
os.environ['PARALLEL_API_KEY'] = 'test_parallel_key'
os.environ['NOVITA_API_KEY'] = 'test_novita_key'

from main import ResearchWorkflow, ResearchState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_question_generation():
    """Test question generation with a sample topic."""
    print("\n" + "="*80)
    print("TEST 1: Question Generation")
    print("="*80)
    
    # Mock the question generator
    mock_questions = [
        "What are the current leading renewable energy storage technologies?",
        "How do lithium-ion batteries compare to other storage solutions?",
        "What are the emerging technologies in energy storage?",
        "What are the economic considerations for renewable energy storage?",
        "What are the environmental impacts of different storage technologies?"
    ]
    
    with patch('main.QuestionGenerator') as MockQG:
        mock_qg = MockQG.return_value
        mock_qg.generate_questions.return_value = mock_questions
        
        workflow = ResearchWorkflow()
        
        state: ResearchState = {
            "topic": "renewable energy storage technologies",
            "questions": [],
            "research_results": [],
            "final_report": None,
            "step": "initial"
        }
        
        state = workflow.generate_questions(state)
        
        assert state["step"] == "generate_questions"
        assert len(state["questions"]) == 5
        assert state["questions"] == mock_questions
        
        print(f"✓ Generated {len(state['questions'])} questions")
        for i, q in enumerate(state['questions'], 1):
            print(f"  {i}. {q}")
    
    print("TEST 1 PASSED\n")


def test_research_execution():
    """Test research execution with mocked API."""
    print("="*80)
    print("TEST 2: Research Execution")
    print("="*80)
    
    # Mock research results
    mock_results = [
        {
            "question": "What are renewable energy storage technologies?",
            "answer": "Renewable energy storage technologies include battery systems, pumped hydro, compressed air, and thermal storage.",
            "citations": [
                {"title": "Energy Storage Overview", "url": "https://example.com/1"},
                {"title": "Battery Technologies", "url": "https://example.com/2"}
            ],
            "status": "completed"
        },
        {
            "question": "How efficient are these technologies?",
            "answer": "Efficiency varies: lithium-ion batteries are 85-95% efficient, pumped hydro is 70-85%, and compressed air is 40-70%.",
            "citations": [
                {"title": "Storage Efficiency Study", "url": "https://example.com/3"}
            ],
            "status": "completed"
        }
    ]
    
    with patch('main.ParallelResearchClient') as MockPRC:
        mock_prc = MockPRC.return_value
        mock_prc.research_multiple.return_value = mock_results
        
        workflow = ResearchWorkflow()
        
        state: ResearchState = {
            "topic": "renewable energy storage",
            "questions": [r["question"] for r in mock_results],
            "research_results": [],
            "final_report": None,
            "step": "generate_questions"
        }
        
        state = workflow.conduct_research(state)
        
        assert state["step"] == "conduct_research"
        assert len(state["research_results"]) == 2
        assert all(r["status"] == "completed" for r in state["research_results"])
        
        print(f"✓ Completed research for {len(state['research_results'])} questions")
        for i, result in enumerate(state['research_results'], 1):
            print(f"  {i}. {result['question']}")
            print(f"     Status: {result['status']}, Citations: {len(result['citations'])}")
    
    print("TEST 2 PASSED\n")


def test_result_synthesis():
    """Test result synthesis into final report."""
    print("="*80)
    print("TEST 3: Result Synthesis")
    print("="*80)
    
    with patch('main.QuestionGenerator'), patch('main.ParallelResearchClient'):
        workflow = ResearchWorkflow()
        
        state: ResearchState = {
            "topic": "renewable energy storage",
            "questions": [
                "What are the main technologies?",
                "What are the costs?"
            ],
            "research_results": [
                {
                    "question": "What are the main technologies?",
                    "answer": "Battery, hydro, and thermal storage.",
                    "citations": [{"title": "Source 1", "url": "https://example.com/1"}],
                    "status": "completed"
                },
                {
                    "question": "What are the costs?",
                    "answer": "Costs range from $100-500/kWh depending on technology.",
                    "citations": [{"title": "Source 2", "url": "https://example.com/2"}],
                    "status": "completed"
                }
            ],
            "final_report": None,
            "step": "conduct_research"
        }
        
        state = workflow.synthesize_results(state)
        
        assert state["step"] == "synthesize_results"
        assert state["final_report"] is not None
        assert "Research Report" in state["final_report"]
        assert "renewable energy storage" in state["final_report"]
        assert "What are the main technologies?" in state["final_report"]
        
        print("✓ Generated final report")
        print(f"  Report length: {len(state['final_report'])} characters")
        print(f"  Contains {state['final_report'].count('###')} sections")
    
    print("TEST 3 PASSED\n")


def test_state_transitions():
    """Test state transitions through the workflow."""
    print("="*80)
    print("TEST 4: State Transitions")
    print("="*80)
    
    mock_questions = ["Question 1?", "Question 2?"]
    mock_results = [
        {"question": "Question 1?", "answer": "Answer 1", "citations": [], "status": "completed"},
        {"question": "Question 2?", "answer": "Answer 2", "citations": [], "status": "completed"}
    ]
    
    with patch('main.QuestionGenerator') as MockQG, \
         patch('main.ParallelResearchClient') as MockPRC:
        
        mock_qg = MockQG.return_value
        mock_qg.generate_questions.return_value = mock_questions
        
        mock_prc = MockPRC.return_value
        mock_prc.research_multiple.return_value = mock_results
        
        workflow = ResearchWorkflow()
        result = workflow.run("test topic")
        
        assert result["topic"] == "test topic"
        assert result["questions"] == mock_questions
        assert len(result["research_results"]) == 2
        assert result["final_report"] is not None
        assert result["step"] == "synthesize_results"
        
        print("✓ Workflow completed all state transitions")
        print(f"  Initial topic: {result['topic']}")
        print(f"  Questions generated: {len(result['questions'])}")
        print(f"  Research completed: {len(result['research_results'])}")
        print(f"  Final step: {result['step']}")
    
    print("TEST 4 PASSED\n")


def test_output_formatting():
    """Test output formatting of the final report."""
    print("="*80)
    print("TEST 5: Output Formatting")
    print("="*80)
    
    with patch('main.QuestionGenerator'), patch('main.ParallelResearchClient'):
        workflow = ResearchWorkflow()
        
        report = workflow._create_report(
            topic="Test Topic",
            questions=["Q1?", "Q2?"],
            results=[
                {
                    "question": "Q1?",
                    "answer": "Answer 1 with details.",
                    "citations": [
                        {"title": "Source 1", "url": "https://example.com/1"},
                        {"title": "Source 2", "url": "https://example.com/2"}
                    ],
                    "status": "completed"
                },
                {
                    "question": "Q2?",
                    "answer": "Answer 2 with information.",
                    "citations": [],
                    "status": "completed"
                }
            ]
        )
        
        # Verify report structure
        assert "# Research Report: Test Topic" in report
        assert "## Executive Summary" in report
        assert "## Detailed Findings" in report
        assert "### 1. Q1?" in report
        assert "### 2. Q2?" in report
        assert "## Conclusion" in report
        assert "[Source 1](https://example.com/1)" in report
        
        print("✓ Report formatting validated")
        print(f"  Has title section: ✓")
        print(f"  Has executive summary: ✓")
        print(f"  Has detailed findings: ✓")
        print(f"  Has conclusion: ✓")
        print(f"  Has citations: ✓")
    
    print("TEST 5 PASSED\n")


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("LANGGRAPH DEEP RESEARCH - TEST SUITE")
    print("="*80)
    print("\nRunning tests without actual API calls (using mocks)...\n")
    
    try:
        test_question_generation()
        test_research_execution()
        test_result_synthesis()
        test_state_transitions()
        test_output_formatting()
        
        print("="*80)
        print("ALL TESTS PASSED ✓")
        print("="*80)
        print("\nThe workflow is ready to use with real API keys.")
        print("Run example.py to see it in action with actual APIs.\n")
        
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {str(e)}\n")
        raise
    except Exception as e:
        print(f"\n✗ ERROR: {str(e)}\n")
        raise


if __name__ == "__main__":
    main()
