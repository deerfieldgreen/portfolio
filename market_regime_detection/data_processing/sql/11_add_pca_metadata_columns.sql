-- Add PCA metadata and HMM parameter columns to mr_transition_matrices.
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_transition_matrices ADD COLUMN IF NOT EXISTS pca_explained_variance Array(Float32) DEFAULT [];
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_transition_matrices ADD COLUMN IF NOT EXISTS pca_n_components UInt8 DEFAULT 0;
ALTER TABLE ${CLICKHOUSE_DATABASE}.mr_transition_matrices ADD COLUMN IF NOT EXISTS hmm_params String DEFAULT '';
