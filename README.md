# RetailIQ — Business Profitability & Decision Intelligence

RetailIQ is a Streamlit analytics app for the Sample Superstore transaction dataset. It supports six focused views for executive performance, product profitability, discounts, customers, scenario sensitivity, and data quality. The interface uses a compact sidebar, shared filters, restrained styling, and Plotly charts.

## Dataset setup

Download `Sample - Superstore.csv` from the [Kaggle Sample Superstore dataset](https://www.kaggle.com/datasets/vivek468/superstore-dataset-final). Place it at `data/raw/Sample - Superstore.csv`, or upload a CSV in the app. The app maps common Superstore column labels and requires Order Date, Sales, and Profit. No replacement data is generated. This repository does not include the dataset.

## Run locally

Python 3.11 or later is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

The app works in CSV-only mode without PostgreSQL. Upload data through the sidebar or use the documented local path.

## PostgreSQL (optional)

Create a PostgreSQL database, copy `.env.example` to `.env`, and set `DATABASE_URL` to your own connection URL. Load an already prepared dataframe using `src.database.postgres.load_table(frame, if_exists="replace")` or `append`. Never commit `.env`. SQL examples in `sql/analytics.sql` operate on the normalized `superstore` table and are inspectable independently; the Streamlit demo does not require the database.

## Analysis and metric definitions

- Sales and profit are summed from source values; profit means the dataset's recorded profit measure.
- Margin = total profit / total sales. Zero total sales yields no margin.
- Orders counts distinct order IDs when available, otherwise rows. Average order value = sales / order count.
- Negative profit is preserved. Duplicate rows are reported but not automatically removed. Invalid dates and numbers become missing.
- Scenario results are sensitivity estimates based on explicit assumptions. There is no demand elasticity or verified cost model.

The SQL collection demonstrates grouping, CASE, CTEs, date truncation, NULLIF, and window functions, answering 14 business questions. The dashboard avoids causal claims about discounting. Product costs, inventory, and stockout risk are not available.

## Project structure

`app.py` and `pages/` provide the interface; reusable transformations live under `src/data`; metrics and simulation under `src/analytics`; optional database access under `src/database`; SQL analyses under `sql`; unit tests under `tests`.

## Tests

```powershell
pytest
```

Tests use small synthetic fixtures only. No real-data result is claimed until you provide the source CSV.

## Deployment

For Streamlit Community Cloud, push the project without the dataset or `.env`, configure `requirements.txt`, and set any production secrets in the platform settings. Users can upload the CSV at runtime. Configure PostgreSQL separately only if needed. Test deployment against the actual dataset and confirm the dataset license and redistribution terms before publishing any copy.

## Screenshots

Screenshots will be added after validating the application with the actual source dataset.
