"""
All metric calculations. Error in pips.
Evaluator uses these — zero LLM calls.
"""
import numpy as np
from typing import Dict


def rmse_pips(y_true: np.ndarray, y_pred: np.ndarray, pip_size: float) -> float:
    """Root Mean Squared Error in pips."""
    errors = (y_true - y_pred) / pip_size
    return float(np.sqrt(np.mean(errors ** 2)))


def mae_pips(y_true: np.ndarray, y_pred: np.ndarray, pip_size: float) -> float:
    """Mean Absolute Error in pips."""
    errors = np.abs(y_true - y_pred) / pip_size
    return float(np.mean(errors))


def directional_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Fraction of correct direction predictions."""
    if len(y_true) < 2:
        return 0.0
    true_dir = np.sign(np.diff(y_true))
    pred_dir = np.sign(np.diff(y_pred))
    return float(np.mean(true_dir == pred_dir))


def sharpe_ratio(returns: np.ndarray, periods_per_year: int = 252) -> float:
    """Annualized Sharpe ratio."""
    if len(returns) < 2 or np.std(returns) == 0:
        return 0.0
    return float(np.mean(returns) / np.std(returns) * np.sqrt(periods_per_year))


def profit_factor(returns: np.ndarray) -> float:
    """Gross profit / gross loss."""
    gains = returns[returns > 0].sum()
    losses = abs(returns[returns < 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def max_drawdown(equity_curve: np.ndarray) -> float:
    """Maximum drawdown as a fraction."""
    peak = np.maximum.accumulate(equity_curve)
    drawdown = (peak - equity_curve) / np.where(peak > 0, peak, 1)
    return float(np.max(drawdown)) if len(drawdown) > 0 else 0.0


def compute_all_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    pip_size: float,
) -> Dict[str, float]:
    """Compute all metrics. Returns dict."""
    # Simple strategy returns: go long if pred > current
    pred_returns = np.diff(y_pred) / y_pred[:-1]
    actual_returns = np.diff(y_true) / y_true[:-1]
    strategy_returns = np.sign(pred_returns) * actual_returns

    equity = np.cumprod(1 + strategy_returns)

    return {
        "rmse_pips": rmse_pips(y_true, y_pred, pip_size),
        "mae_pips": mae_pips(y_true, y_pred, pip_size),
        "directional_accuracy": directional_accuracy(y_true, y_pred),
        "sharpe": sharpe_ratio(strategy_returns),
        "profit_factor": profit_factor(strategy_returns),
        "max_drawdown": max_drawdown(equity),
    }
