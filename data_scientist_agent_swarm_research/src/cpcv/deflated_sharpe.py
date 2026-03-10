"""
Deflated Sharpe Ratio (DSR).
López de Prado (2014) — adjusts for multiple testing.
"""
import numpy as np
from scipy import stats


def deflated_sharpe_ratio(
    sharpe: float,
    n_trials: int,
    n_observations: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    sharpe_benchmark: float = 0.0,
) -> float:
    """
    Compute the Deflated Sharpe Ratio.
    
    Adjusts for:
    1. Multiple testing (n_trials)
    2. Non-normal returns (skewness, kurtosis)
    3. Short track records (n_observations)
    
    Returns: probability that the observed Sharpe is genuine (0 to 1).
    """
    if n_observations < 2 or n_trials < 1:
        return 0.0

    # Expected maximum Sharpe under null
    e_max_sharpe = _expected_max_sharpe(n_trials, n_observations)

    # Standard error of Sharpe
    se = np.sqrt(
        (1 - skewness * sharpe + ((kurtosis - 1) / 4) * sharpe ** 2)
        / (n_observations - 1)
    )

    if se == 0:
        return 0.0

    # Test statistic
    z = (sharpe - e_max_sharpe) / se

    return float(stats.norm.cdf(z))


def _expected_max_sharpe(n_trials: int, n_observations: int) -> float:
    """Expected maximum Sharpe ratio under the null hypothesis."""
    if n_trials <= 1:
        return 0.0

    gamma = 0.5772156649  # Euler-Mascheroni constant
    z = stats.norm.ppf(1 - 1 / n_trials)

    e_max = z * (1 - gamma) + gamma * stats.norm.ppf(1 - 1 / (n_trials * np.e))
    se_max = e_max / np.sqrt(n_observations)

    return float(se_max)
