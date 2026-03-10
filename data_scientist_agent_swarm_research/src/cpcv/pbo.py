"""
Probability of Backtest Overfitting (PBO).
Bailey et al. (2017).
"""
import numpy as np
from itertools import combinations
from typing import List, Tuple


def compute_pbo(
    performance_matrix: np.ndarray,
    n_partitions: int = 10,
) -> float:
    """
    Compute PBO using the Combinatorially Symmetric Cross-Validation (CSCV) method.
    
    Args:
        performance_matrix: (n_strategies, n_partitions) matrix of OOS performance
        n_partitions: number of time partitions
    
    Returns:
        PBO value between 0 and 1. Lower is better.
        PBO > 0.5 suggests overfitting.
    """
    n_strategies, n_parts = performance_matrix.shape
    if n_parts < 4:
        return 1.0  # not enough partitions

    half = n_parts // 2
    overfit_count = 0
    total_combos = 0

    for train_combo in combinations(range(n_parts), half):
        test_combo = tuple(i for i in range(n_parts) if i not in train_combo)

        # In-sample performance
        is_perf = performance_matrix[:, list(train_combo)].mean(axis=1)
        # Out-of-sample performance
        oos_perf = performance_matrix[:, list(test_combo)].mean(axis=1)

        # Best in-sample strategy
        best_is = np.argmax(is_perf)

        # Rank of best-IS strategy in OOS
        oos_rank = np.sum(oos_perf >= oos_perf[best_is])

        # If best IS strategy is in bottom half OOS, it's overfit
        if oos_rank > n_strategies / 2:
            overfit_count += 1

        total_combos += 1

    return float(overfit_count / max(total_combos, 1))
