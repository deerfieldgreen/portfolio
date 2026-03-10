-- Rename macro columns from misleading *_diff names to *_us (US-only FRED series, no differential).
-- Run once on existing tables. No-op if columns already have the new names.
-- ClickHouse RENAME COLUMN requires 20.4+.
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN policy_rate_diff TO policy_rate_us;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN interest_rate_2y_diff TO interest_rate_2y_us;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN interest_rate_10y_diff TO interest_rate_10y_us;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN dgs30_diff TO dgs30_us;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN t10y2y_diff TO t10y2y_us;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN t10y3m_diff TO t10y3m_us;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN t10yie_diff TO t10yie_us;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN sp500_diff TO sp500_us;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN vixcls_diff TO vixcls_us;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN dtwexbgs_diff TO dtwexbgs_us;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN usepuindxd_diff TO usepuindxd_us;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN usrecd_diff TO usrecd_us;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN policy_rate_diff_z TO policy_rate_us_z;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN interest_rate_2y_diff_z TO interest_rate_2y_us_z;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN interest_rate_10y_diff_z TO interest_rate_10y_us_z;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN dgs30_diff_z TO dgs30_us_z;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN t10y2y_diff_z TO t10y2y_us_z;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN t10y3m_diff_z TO t10y3m_us_z;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN t10yie_diff_z TO t10yie_us_z;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN sp500_diff_z TO sp500_us_z;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN vixcls_diff_z TO vixcls_us_z;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN dtwexbgs_diff_z TO dtwexbgs_us_z;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN usepuindxd_diff_z TO usepuindxd_us_z;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states RENAME COLUMN usrecd_diff_z TO usrecd_us_z;
