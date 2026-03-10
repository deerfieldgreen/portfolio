"""Sequence windowing for time series models."""
import numpy as np
from typing import Tuple


def create_sequences(
    data: np.ndarray,
    target: np.ndarray,
    sequence_length: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Create sliding window sequences.
    NEVER create sequences across split boundaries — caller must split first.
    
    Args:
        data: (N, features) array
        target: (N,) array
        sequence_length: window size
    
    Returns:
        X: (N - seq_len, seq_len, features)
        y: (N - seq_len,)
    """
    X, y = [], []
    for i in range(sequence_length, len(data)):
        X.append(data[i - sequence_length : i])
        y.append(target[i])
    return np.array(X), np.array(y)
