"""
AST validation for LLM-generated experiment code.
Import allowlist enforced — new libs need adding here AND to Docker image.
"""
import ast
from typing import List, Tuple


ALLOWED_IMPORTS = {
    "torch", "torch.nn", "torch.optim", "torch.utils.data",
    "numpy", "np",
    "pandas", "pd",
    "sklearn", "sklearn.preprocessing", "sklearn.metrics", "sklearn.model_selection",
    "xgboost", "xgb",
    "optuna",
    "mlflow",
    "os", "sys", "json", "math", "typing", "dataclasses",
    "collections", "itertools", "functools",
    "src.training.scaffolding.data_loader",
    "src.training.scaffolding.training_loop",
    "src.training.scaffolding.metrics",
    "src.training.scaffolding.mlflow_log",
    "src.training.features",
    "src.training.sequences",
    "src.training.walk_forward",
    "src.training.pyfunc_wrapper",
    "src.shared.config",
    "src.shared.ch_client",
    "src.cpcv.purged_cv",
    "src.cpcv.deflated_sharpe",
    "src.cpcv.pbo",
}

BLOCKED_CALLS = {
    "os.system", "os.popen", "os.exec", "os.execvp",
    "subprocess.run", "subprocess.Popen", "subprocess.call",
    "eval", "exec", "compile", "__import__",
    "open",  # only /workspace/ paths allowed
}


def validate_code(code: str) -> Tuple[bool, List[str]]:
    """
    Validate LLM-generated experiment code via AST.
    Returns (is_valid, list_of_issues).
    """
    issues = []

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, [f"Syntax error: {e}"]

    for node in ast.walk(tree):
        # Check imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if alias.name not in ALLOWED_IMPORTS and root not in ALLOWED_IMPORTS:
                    issues.append(f"Blocked import: {alias.name}")

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if node.module not in ALLOWED_IMPORTS and root not in ALLOWED_IMPORTS:
                    issues.append(f"Blocked import: {node.module}")

        # Check blocked function calls
        elif isinstance(node, ast.Call):
            call_name = _get_call_name(node)
            if call_name in BLOCKED_CALLS:
                issues.append(f"Blocked call: {call_name}")

    # Check for run_experiment function
    has_run_experiment = any(
        isinstance(node, ast.FunctionDef) and node.name == "run_experiment"
        for node in ast.walk(tree)
    )
    if not has_run_experiment:
        issues.append("Missing required function: run_experiment()")

    return len(issues) == 0, issues


def _get_call_name(node: ast.Call) -> str:
    """Extract the full call name from an AST Call node."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    elif isinstance(node.func, ast.Attribute):
        parts = []
        current = node.func
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
    return ""
