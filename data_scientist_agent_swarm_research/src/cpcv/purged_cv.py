"""
Combinatorially Purged Cross-Validation (CPCV).
López de Prado, Advances in Financial Machine Learning.
"""
import numpy as np
from itertools import combinations
from typing import List, Tuple


def purged_cv_splits(
    n_samples: int,
    n_splits: int = 5,
    n_test_groups: int = 2,
    purge_gap: int = 10,
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """
    Generate CPCV splits with purge gap.
    
    Args:
        n_samples: total number of samples
        n_splits: number of groups to divide data into
        n_test_groups: number of groups in each test set
        purge_gap: number of samples to remove between train/test
    
    Returns:
        List of (train_idx, test_idx) tuples
    """
    group_size = n_samples // n_splits
    groups = []
    for i in range(n_splits):
        start = i * group_size
        end = start + group_size if i < n_splits - 1 else n_samples
        groups.append(np.arange(start, end))

    splits = []
    for test_combo in combinations(range(n_splits), n_test_groups):
        test_idx = np.concatenate([groups[i] for i in test_combo])

        # Build train indices with purge
        train_groups = [i for i in range(n_splits) if i not in test_combo]
        train_idx = np.concatenate([groups[i] for i in train_groups])

        # Apply purge: remove samples too close to test boundaries
        test_min, test_max = test_idx.min(), test_idx.max()
        purge_mask = (
            (train_idx < test_min - purge_gap) |
            (train_idx > test_max + purge_gap)
        )
        train_idx = train_idx[purge_mask]

        if len(train_idx) > 0 and len(test_idx) > 0:
            splits.append((train_idx, test_idx))

    return splits
