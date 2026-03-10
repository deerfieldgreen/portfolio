-- Add FRED macro columns to existing mr_regime_states (run once for tables created before this change).
-- ClickHouse 22.8+: ADD COLUMN IF NOT EXISTS. Older: run each ALTER, ignore "column exists" errors.
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states ADD COLUMN IF NOT EXISTS dgs30_us Nullable(Float32);
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states ADD COLUMN IF NOT EXISTS t10y2y_us Nullable(Float32);
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states ADD COLUMN IF NOT EXISTS t10y3m_us Nullable(Float32);
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states ADD COLUMN IF NOT EXISTS t10yie_us Nullable(Float32);
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states ADD COLUMN IF NOT EXISTS sp500_us Nullable(Float32);
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states ADD COLUMN IF NOT EXISTS vixcls_us Nullable(Float32);
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states ADD COLUMN IF NOT EXISTS dtwexbgs_us Nullable(Float32);
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states ADD COLUMN IF NOT EXISTS usepuindxd_us Nullable(Float32);
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states ADD COLUMN IF NOT EXISTS usrecd_us Nullable(Float32);
