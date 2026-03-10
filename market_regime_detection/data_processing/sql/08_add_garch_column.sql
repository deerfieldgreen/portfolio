-- Add GARCH(1,1) conditional volatility diagnostic column to mr_regime_states.
-- Values stored as percentage-scaled (log_return * 100) to match arch model output units.
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_regime_states ADD COLUMN IF NOT EXISTS garch_conditional_volatility Nullable(Float32);
