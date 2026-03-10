"""
Validate training data quality before training.
Runs in fx-ops image.
"""
import os, sys
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import pandas as pd
import numpy as np


def main():
    data_path = os.environ.get("DATA_PATH", "/workspace/data.parquet")

    df = pd.read_parquet(data_path)
    issues = []

    # Check minimum rows
    min_rows = 1000
    if len(df) < min_rows:
        issues.append(f"Insufficient data: {len(df)} rows (min {min_rows})")

    # Check for NaN
    nan_cols = df.columns[df.isna().any()].tolist()
    if nan_cols:
        issues.append(f"NaN in columns: {nan_cols[:10]}")

    # Check for Inf
    numeric = df.select_dtypes(include=[np.number])
    inf_cols = numeric.columns[np.isinf(numeric).any()].tolist()
    if inf_cols:
        issues.append(f"Inf in columns: {inf_cols[:10]}")

    # Check for zero-variance columns
    zero_var = numeric.columns[numeric.std() == 0].tolist()
    if zero_var:
        issues.append(f"Zero-variance columns: {zero_var[:10]}")

    # Check timestamp monotonicity
    if "timestamp" in df.columns:
        if not df["timestamp"].is_monotonic_increasing:
            issues.append("Timestamps not monotonically increasing")

    if issues:
        print("DATA VALIDATION FAILED:")
        for issue in issues:
            print(f"  - {issue}")
        sys.exit(1)
    else:
        print(f"Data validation passed: {len(df)} rows, {len(df.columns)} columns")


if __name__ == "__main__":
    main()
