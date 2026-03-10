-- Add model-level quality metrics to mr_transition_matrices so /validate can query one source of truth.
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_transition_matrices ADD COLUMN IF NOT EXISTS aic Float32 DEFAULT 0;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_transition_matrices ADD COLUMN IF NOT EXISTS bic Float32 DEFAULT 0;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_transition_matrices ADD COLUMN IF NOT EXISTS log_likelihood Float32 DEFAULT 0;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_transition_matrices ADD COLUMN IF NOT EXISTS avg_confidence Float32 DEFAULT 0;
