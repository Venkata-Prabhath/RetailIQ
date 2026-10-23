# RetailIQ

RetailIQ is a Streamlit dashboard and repeatable batch analytics workflow for the historical Sample Superstore dataset. The supplied file covers 2014–2017 transaction dates and is a static sample, not a live feed.

## Architecture and workflow

`CSV ingestion → column normalization and validation → rejected-row flags / valid transactions → idempotent PostgreSQL upsert (optional) → KPI and anomaly analysis → CSV, Excel, and PDF management reports → optional SMTP delivery`

The existing six dashboard pages remain available. Dashboard uploads are limited to 50 MB. Uploaded CSV headings are inferred locally from known aliases, semantic name matches, and sample value types; a mapping editor lets you review or correct them before analysis. High-confidence mappings are applied automatically, and ambiguous required fields must be mapped by the user. The same high-confidence inference is available to the reusable pipeline and CLI. The dashboard defaults to local CSV mode. `DATA_SOURCE=postgres` explicitly selects the PostgreSQL transaction table for the dashboard.

## Structure

- `app.py`: six-page Streamlit dashboard and downloadable reports
- `src/data/pipeline.py`: ingestion, normalization, validation, row keys, source summaries
- `src/data/schema.py`: local schema inference, candidate confidence, explicit source-to-RetailIQ field mapping
- `src/analytics/metrics.py`: KPI, grouped, monthly, simulator, period comparisons
- `src/analytics/anomalies.py`: explainable monthly and negative-profit checks
- `src/database/postgres.py`: repeatable schema and transactional idempotent persistence
- `src/reporting/reports.py`: report calculation and CSV, XLSX, PDF export
- `src/cli.py`: standalone batch command, logging, optional email delivery
- `sql/schema.sql`, `sql/analytics.sql`: schema and query examples

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
streamlit run app.py
```

Place the CSV at `data/raw/Sample - Superstore.csv` or upload one in the app. The CLI and dashboard load an optional local `.env`; process environment variables take precedence.

## Batch reports

```powershell
python -m src.cli --source "data/raw/Sample - Superstore.csv"
python -m src.cli --source "data/raw/Sample - Superstore.csv" --weekly --email
```

The command writes `reports/retailiq_management_report.pdf`, `.xlsx`, a regional `.csv`, a rejected-row quarantine CSV, `last_run.json`, and structured `pipeline.log`. The same source file is fingerprinted and PostgreSQL loading is skipped if already successfully ingested; report generation may still be repeated. Use a new changed source snapshot for new ingestion. A historical sample should not be presented as daily incoming transactions.

For daily execution, schedule the first command in Windows Task Scheduler or cron. For weekly management delivery, schedule the `--weekly --email` command once per week. The weekly option labels the report frequency; it does not manufacture a rolling week from a historical snapshot. Configure task working directory as the repository root. Set `REPORT_EMAIL_TO` only to an approved recipient.

## PostgreSQL

CSV-only operation requires no database. To enable PostgreSQL, set `DATABASE_URL`, then run any CLI batch (repeatable schema initialization occurs automatically). Transaction records use `Row ID` when present and unique. `Order ID` is not a transaction key because multiple line items belong to the same order. Other datasets use a SHA-256 fingerprint of normalized row values plus a duplicate occurrence number, which preserves identical source rows while making retries idempotent.

Tables: `retail_transactions`, `pipeline_runs`, `data_quality_results`, and `kpi_snapshots`. Writes use a transaction and key-based upserts; no routine execution drops tables. Rejected rows are counted and reported but excluded from the processed transaction table. Stable source row IDs support correction updates. Content-fingerprint keys cannot identify changed versions of a transaction when a source has no stable key; source deletions are not inferred from incremental batches. `DATA_SOURCE=postgres` selects the processed database table in Streamlit.

For local Docker, `docker compose up --build` starts PostgreSQL with a persistent volume and a health check. The default password is for local development only. Change `POSTGRES_PASSWORD` for a private deployment; do not expose this compose service to the public internet.

## Email configuration

Set `SMTP_HOST`, `SMTP_PORT` (typically 587), `SMTP_USER`, `SMTP_PASSWORD`, `REPORT_EMAIL_FROM`, and `REPORT_EMAIL_TO` in the scheduler's secret environment. Delivery uses STARTTLS. Email is disabled unless `--email` is supplied and a recipient is configured. Failures are logged; the CLI attempts a concise failure notification when email is enabled.

## Metric, data, and anomaly notes

- Required concepts: transaction date, sales/revenue, and profit/earnings. Common aliases and recognizable synonyms are inferred; the upload mapping editor handles unfamiliar headings. If neither names nor values identify a role, it must be mapped manually. Invalid dates and missing or malformed required numeric measures are marked rejected; source rows remain in the quality counts.
- Negative profit is retained. Duplicate source rows are retained and reported.
- Margin is total recorded profit divided by total sales. Average order value is sales divided by distinct order IDs.
- Period comparisons use the immediately preceding window with the same number of calendar days. Zero or missing baselines produce unavailable percentage changes.
- Management reports summarize the trailing 365 calendar days through the latest valid transaction date and compare against the preceding 365 days. Monthly anomalies compare with the preceding three observed monthly buckets and use configurable drop/spike percentages in `detect_anomalies`. Regional/category alerts flag significant monthly movement, product alerts flag cumulative losses, and repeat-run quality alerts flag rejection-rate deterioration. Alerts identify a review need, not its cause.
- Customer repeat order analysis is supported when customer and order identifiers exist. Data does not establish discount causality, stock risk, or demand elasticity.

## Tests

```powershell
python -m pytest -q
```

Tests cover transformations, period comparisons, anomaly thresholds, report exports, and CLI behavior. PostgreSQL integration requires a separately configured test database; by default database behavior is verified through isolated/mocked tests.

## Deployment

Streamlit Community Cloud can host the dashboard. Because the supplied dataset is ignored by Git, configure the app secret `SUPERSTORE_CSV_URL` to a stable HTTPS source or upload a CSV for the session. It does not provide a persistent PostgreSQL service, scheduler, or SMTP relay. Run batch jobs, PostgreSQL, and SMTP from separately managed infrastructure (for example a private VM/container host plus OS scheduler). Configure secrets in the deployment's secret manager. Keep dashboard hosting instructions separate from the local Docker workflow.

## Limitations

This project uses a historical sample dataset and recorded values. Repeated runs do not turn it into a live feed. Source file licensing and permitted redistribution must be confirmed by the operator. Missing comparison history, customer identity, or fields are shown as unavailable rather than imputed.
