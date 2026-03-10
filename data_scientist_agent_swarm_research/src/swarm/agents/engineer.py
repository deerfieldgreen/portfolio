"""
Engineer agent. Generates experiment code from specs using Jinja2 templates.
Uses analysis model (qwen3.5-397b).
"""
import json
from pathlib import Path
from src.shared.llm_client import chat_analysis
from src.swarm.state import SwarmState
from src.swarm.sandbox import validate_code

SYSTEM_PROMPT = Path(__file__).parent.parent / "prompts" / "engineer_system.md"
USER_PROMPT = Path(__file__).parent.parent / "prompts" / "engineer_user.md"


def run_engineer(state: SwarmState) -> dict:
    """Generate experiment code for each spec. Returns generated_code dict."""
    generated_code = {}

    system = SYSTEM_PROMPT.read_text() if SYSTEM_PROMPT.exists() else "You are the Engineer agent."

    for spec in state.experiment_specs:
        exp_id = spec.get("experiment_id", "unknown")

        user_content = json.dumps(spec, indent=2, default=str)
        if USER_PROMPT.exists():
            user_content = USER_PROMPT.read_text().format(
                experiment_spec_json=user_content,
            )

        response = chat_analysis(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=8192,
        )

        # Extract code from response
        code = _extract_code(response)

        # Validate via AST sandbox
        is_valid, issues = validate_code(code)
        if not is_valid:
            # Retry once with feedback
            retry_msg = f"Code validation failed:\n" + "\n".join(issues) + "\nFix these issues."
            response = chat_analysis(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": response},
                    {"role": "user", "content": retry_msg},
                ],
                temperature=0.2,
                max_tokens=8192,
            )
            code = _extract_code(response)
            is_valid, issues = validate_code(code)

        if is_valid:
            generated_code[exp_id] = code
        else:
            generated_code[exp_id] = _fallback_code(spec, issues)

    return {"generated_code": generated_code}


def _extract_code(response: str) -> str:
    """Extract Python code from LLM response."""
    if "```python" in response:
        parts = response.split("```python")
        if len(parts) > 1:
            code = parts[1].split("```")[0]
            return code.strip()
    if "```" in response:
        parts = response.split("```")
        if len(parts) > 2:
            return parts[1].strip()
    return response.strip()


def _fallback_code(spec: dict, issues: list) -> str:
    """Generate a minimal fallback experiment that logs the failure."""
    return f'''
"""Fallback experiment — code generation failed."""
import mlflow

def run_experiment():
    with mlflow.start_run():
        mlflow.log_param("status", "code_gen_failed")
        mlflow.log_param("architecture", "{spec.get('architecture', 'unknown')}")
        mlflow.log_param("issues", "{'; '.join(issues[:3])}")
        mlflow.log_metric("sharpe", 0.0)
        mlflow.log_metric("directional_accuracy", 0.0)
    print("Fallback experiment: code generation failed")
    print("Issues: {'; '.join(issues[:3])}")
'''
