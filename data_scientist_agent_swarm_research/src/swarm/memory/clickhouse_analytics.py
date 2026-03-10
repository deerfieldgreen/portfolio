"""ClickHouse analytics queries for experiment history."""
from src.shared.ch_client import get_client


def get_recent_experiments(limit: int = 50) -> list:
    """Get recent experiments for context."""
    ch = get_client()
    result = ch.query(
        "SELECT run_id, experiment_id, architecture, model_family, "
        "strategy_type, pair, timeframe, metrics, status, "
        "directional_accuracy, deflated_sharpe, pbo, novelty_score "
        "FROM fxs_experiments "
        "ORDER BY timestamp DESC "
        "LIMIT %(limit)s",
        parameters={"limit": limit},
    )
    return [dict(r) for r in result.named_results()]


def get_best_experiments_by_direction(direction: str, limit: int = 5) -> list:
    """Get best experiments for a research direction."""
    ch = get_client()
    result = ch.query(
        "SELECT run_id, architecture, strategy_type, "
        "metrics, deflated_sharpe, directional_accuracy "
        "FROM fxs_experiments "
        "WHERE research_direction = %(dir)s AND status = 'success' "
        "ORDER BY deflated_sharpe DESC "
        "LIMIT %(limit)s",
        parameters={"dir": direction, "limit": limit},
    )
    return [dict(r) for r in result.named_results()]


def get_failure_patterns() -> list:
    """Analyze common failure modes."""
    ch = get_client()
    result = ch.query(
        "SELECT status, architecture, count() as cnt, "
        "avg(directional_accuracy) as avg_da "
        "FROM fxs_experiments "
        "WHERE status != 'success' "
        "GROUP BY status, architecture "
        "ORDER BY cnt DESC "
        "LIMIT 20"
    )
    return [dict(r) for r in result.named_results()]


def log_experiment(experiment_data: dict):
    """Write experiment record to ClickHouse."""
    ch = get_client()
    ch.insert(
        "fxs_experiments",
        data=[list(experiment_data.values())],
        column_names=list(experiment_data.keys()),
    )
