"""
Example script demonstrating the LangGraph Deep Research workflow.

Shows two usage patterns:
1. Streaming  — real-time output via workflow.stream()
2. Blocking   — full result via workflow.run()
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


def run_streaming_example(topic: str) -> None:
    """Run research workflow with streaming output."""
    print()
    print_separator()
    print("LANGGRAPH DEEP RESEARCH — STREAMING MODE")
    print_separator()
    print(f"Topic: {topic}")
    print()

    workflow = create_workflow()

    print("Starting streaming research...\n")
    print_separator("-")
    print()

    for event in workflow.stream(topic):
        event_type = event["type"]

        if event_type == "status":
            print(f"\n[{event['message']}]")
            if "questions" in event:
                for i, q in enumerate(event["questions"], 1):
                    print(f"  {i}. {q}")

        elif event_type == "token":
            # Print synthesis tokens as they arrive — no newline so they flow
            print(event["content"], end="", flush=True)

        elif event_type == "complete":
            state = event["state"]
            print("\n")
            print_separator()
            print(
                f"Done. {len(state['research_results'])} questions researched, "
                f"report is {len(state.get('final_report', ''))} characters."
            )
            print_separator()


def run_blocking_example(topic: str) -> None:
    """Run research workflow and display results after completion."""
    print()
    print_separator()
    print("LANGGRAPH DEEP RESEARCH — BLOCKING MODE")
    print_separator()
    print(f"Topic: {topic}")
    print()

    workflow = create_workflow()
    print("Running research workflow (this may take a few minutes)...\n")

    result = workflow.run(topic)

    print_separator()
    print("GENERATED RESEARCH QUESTIONS")
    print_separator()
    for i, q in enumerate(result["questions"], 1):
        print(f"{i}. {q}")
    print()

    print_separator()
    print("RESEARCH RESULTS")
    print_separator()
    for i, r in enumerate(result["research_results"], 1):
        print(f"Question {i}: {r['question']}")
        print(f"Status: {r['status']}")
        if r.get("answer"):
            preview = r["answer"][:200]
            if len(r["answer"]) > 200:
                preview += "..."
            print(f"Answer preview: {preview}")
        if r.get("citations"):
            print(f"Citations: {len(r['citations'])} sources")
        if r.get("error"):
            print(f"Error: {r['error']}")
        print()

    if result["final_report"]:
        print_separator()
        print("FINAL RESEARCH REPORT")
        print_separator()
        print(result["final_report"])

    print_separator()
    print("Research workflow completed successfully!")
    print_separator()


def main():
    """Run the streaming example by default."""
    topic = "renewable energy storage technologies"

    try:
        run_streaming_example(topic)
    except Exception as e:
        print()
        print_separator()
        print(f"ERROR: {str(e)}")
        print_separator()
        print()
        print("Make sure you have:")
        print("1. Set PARALLEL_API_KEY in your environment")
        print("2. Set NOVITA_API_KEY in your environment")
        print("3. Installed all requirements: pip install -r requirements.txt")
        sys.exit(1)


if __name__ == "__main__":
    main()
