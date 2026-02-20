"""
Example script demonstrating the LangGraph Deep Research workflow.

This script shows how to:
1. Initialize the research workflow
2. Run research on a specific topic
3. Display results with progress tracking
4. Pretty-print the final report
"""

import logging
import sys
from main import create_workflow

# Configure logging to show progress
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)


def print_separator(char="=", length=80):
    """Print a separator line."""
    print(char * length)


def print_questions(questions):
    """Pretty-print generated questions."""
    print_separator()
    print("GENERATED RESEARCH QUESTIONS")
    print_separator()
    print()
    for i, question in enumerate(questions, 1):
        print(f"{i}. {question}")
    print()


def print_research_progress(results):
    """Print research progress and summaries."""
    print_separator()
    print("RESEARCH RESULTS")
    print_separator()
    print()
    
    for i, result in enumerate(results, 1):
        print(f"Question {i}: {result['question']}")
        print(f"Status: {result['status']}")
        
        if result.get('answer'):
            # Print first 200 characters of the answer
            answer_preview = result['answer'][:200]
            if len(result['answer']) > 200:
                answer_preview += "..."
            print(f"Answer preview: {answer_preview}")
        
        citations = result.get('citations', [])
        if citations:
            print(f"Citations: {len(citations)} sources")
        
        if result.get('error'):
            print(f"Error: {result['error']}")
        
        print()


def print_final_report(report):
    """Pretty-print the final report."""
    print_separator("=")
    print("FINAL RESEARCH REPORT")
    print_separator("=")
    print()
    print(report)
    print()


def main():
    """Run the example research workflow."""
    # Research topic
    topic = "renewable energy storage technologies"
    
    print()
    print_separator("=")
    print(f"LANGGRAPH DEEP RESEARCH EXAMPLE")
    print_separator("=")
    print()
    print(f"Research Topic: {topic}")
    print()
    print("This example demonstrates a complete research workflow:")
    print("1. Generate focused research questions (Novita AI - Qwen 3.5 397B)")
    print("2. Conduct deep research for each question (Parallel AI)")
    print("3. Synthesize findings into a comprehensive report")
    print()
    
    try:
        # Create and run the workflow
        print("Initializing workflow...")
        workflow = create_workflow()
        
        print(f"Starting research on: {topic}")
        print()
        
        # Run the workflow
        result = workflow.run(topic)
        
        # Display results step by step
        print()
        print_questions(result['questions'])
        
        print_research_progress(result['research_results'])
        
        if result['final_report']:
            print_final_report(result['final_report'])
        
        print_separator("=")
        print("Research workflow completed successfully!")
        print_separator("=")
        
    except Exception as e:
        print()
        print_separator("=")
        print(f"ERROR: {str(e)}")
        print_separator("=")
        print()
        print("Make sure you have:")
        print("1. Set PARALLEL_API_KEY in your environment")
        print("2. Set NOVITA_API_KEY in your environment")
        print("3. Installed all requirements: pip install -r requirements.txt")
        sys.exit(1)


if __name__ == "__main__":
    main()
