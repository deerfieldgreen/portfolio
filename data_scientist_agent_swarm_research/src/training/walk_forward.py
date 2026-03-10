"""Walk-forward split generation for time series cross-validation."""
from typing import List, Tuple
import numpy as np


def walk_forward_splits(
    n_samples: int,
    train_months: int = 8,
    val_months: int = 2,
    test_months: int = 2,
    step_months: int = 2,
    samples_per_month: int = 500,
) -> List[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """
    Generate walk-forward train/val/test splits.
    
    Returns list of (train_idx, val_idx, test_idx) tuples.
    Each split moves forward by step_months.
    """
    train_size = train_months * samples_per_month
    val_size = val_months * samples_per_month
    test_size = test_months * samples_per_month
    step_size = step_months * samples_per_month
    window = train_size + val_size + test_size

    splits = []
    start = 0
    while start + window <= n_samples:
        train_end = start + train_size
        val_end = train_end + val_size
        test_end = val_end + test_size

        train_idx = np.arange(start, train_end)
        val_idx = np.arange(train_end, val_end)
        test_idx = np.arange(val_end, test_end)

        splits.append((train_idx, val_idx, test_idx))
        start += step_size

    return splits
