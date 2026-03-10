Propose exactly {batch_size} experiments for the next swarm cycle.

## Available Pairs & Timeframes
{available_pairs_json}

## Current Champion Metrics
{champion_metrics_json}

## Bandit Allocation (match this exactly)
{allocation_json}

## Active Insights (hard constraints — do not violate)
{insights_list}

## Similar Past Experiments (avoid repeating these)
{similar_experiments_json}

## Relevant Research (cite by entry_id when applicable)
{relevant_research_json}

## Available Feature Columns
{feature_cols_list}

Respond with a JSON object:
```json
{{
  "experiments": [
    {{
      "experiment_id": "uuid",
      "research_direction": "arch_search|feature_eng|strategy|ensemble|regime|refine",
      "architecture": "e.g. TCN, BiGRU, XGBoost, Transformer, etc.",
      "model_family": "e.g. cnn, rnn, tree, transformer",
      "feature_set": ["list", "of", "feature", "columns"],
      "strategy_type": "descriptive label for the strategy",
      "strategy_description": "detailed description of how the strategy works",
      "pair": "e.g. USD_JPY",
      "timeframe": "e.g. H1",
      "hyperparameter_hints": {{}},
      "reasoning": "why this experiment, citing research",
      "research_references": ["entry_id_1", "entry_id_2"],
      "predicted_sharpe": 0.0
    }}
  ]
}}
```
