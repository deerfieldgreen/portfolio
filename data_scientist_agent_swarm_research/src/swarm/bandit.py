"""
Thompson Sampling bandit for research direction allocation.
Arms: arch_search, feature_eng, strategy, ensemble, regime, refine
"""
import numpy as np
from typing import Dict


ARMS = ["arch_search", "feature_eng", "strategy", "ensemble", "regime", "refine"]


def initialize_bandit() -> Dict:
    """Initialize bandit state with uniform priors."""
    return {arm: {"alpha": 1.0, "beta": 1.0} for arm in ARMS}


def allocate(
    bandit_state: Dict,
    batch_size: int = 4,
    exploration_pct: float = 0.20,
) -> Dict[str, int]:
    """
    Thompson Sampling allocation.
    Returns dict mapping arm name → number of experiments.
    """
    if not bandit_state:
        bandit_state = initialize_bandit()

    n_explore = max(1, int(batch_size * exploration_pct))
    n_exploit = batch_size - n_explore

    # Sample from Beta distributions
    samples = {}
    for arm, params in bandit_state.items():
        samples[arm] = np.random.beta(params["alpha"], params["beta"])

    # Exploit: allocate to highest-sampled arms
    sorted_arms = sorted(samples.keys(), key=lambda a: samples[a], reverse=True)
    allocation = {arm: 0 for arm in ARMS}

    for i in range(n_exploit):
        allocation[sorted_arms[i % len(sorted_arms)]] += 1

    # Explore: spread across underexplored arms
    explore_arms = sorted(
        bandit_state.keys(),
        key=lambda a: bandit_state[a]["alpha"] + bandit_state[a]["beta"],
    )
    for i in range(n_explore):
        allocation[explore_arms[i % len(explore_arms)]] += 1

    return allocation


def update_bandit(
    bandit_state: Dict,
    arm: str,
    reward: float,
) -> Dict:
    """
    Update bandit state based on experiment outcome.
    reward: 1.0 for improvement, 0.0 for no improvement.
    """
    if arm not in bandit_state:
        bandit_state[arm] = {"alpha": 1.0, "beta": 1.0}

    if reward > 0:
        bandit_state[arm]["alpha"] += reward
    else:
        bandit_state[arm]["beta"] += 1.0

    return bandit_state
