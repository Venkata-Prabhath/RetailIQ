-- Repeatable PostgreSQL initialization. No routine DDL drops production data.
CREATE TABLE IF NOT EXISTS retail_transactions (
  record_key TEXT PRIMARY KEY, order_id TEXT, order_date DATE, ship_date DATE, ship_mode TEXT,
  customer_id TEXT, product_id TEXT, product_name TEXT, region TEXT, segment TEXT,
  category TEXT, sub_category TEXT, sales DOUBLE PRECISION, profit DOUBLE PRECISION,
  quantity DOUBLE PRECISION, discount DOUBLE PRECISION, payload JSONB NOT NULL
);
ALTER TABLE retail_transactions ADD COLUMN IF NOT EXISTS ship_mode TEXT;
ALTER TABLE retail_transactions ADD COLUMN IF NOT EXISTS segment TEXT;
CREATE INDEX IF NOT EXISTS ix_retail_transactions_order_date ON retail_transactions(order_date);
CREATE INDEX IF NOT EXISTS ix_retail_transactions_product ON retail_transactions(product_id);
CREATE TABLE IF NOT EXISTS pipeline_runs (
  run_id TEXT PRIMARY KEY, started_at TIMESTAMPTZ NOT NULL, finished_at TIMESTAMPTZ,
  status TEXT NOT NULL, source TEXT NOT NULL, source_fingerprint TEXT NOT NULL,
  source_rows INTEGER NOT NULL, valid_rows INTEGER NOT NULL, rejected_rows INTEGER NOT NULL,
  duplicate_rows INTEGER NOT NULL, summary JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS data_quality_results (
  run_id TEXT PRIMARY KEY REFERENCES pipeline_runs(run_id), result JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS kpi_snapshots (
  run_id TEXT PRIMARY KEY REFERENCES pipeline_runs(run_id), reporting_start DATE,
  reporting_end DATE, sales DOUBLE PRECISION, profit DOUBLE PRECISION, margin DOUBLE PRECISION,
  orders INTEGER, aov DOUBLE PRECISION
);
