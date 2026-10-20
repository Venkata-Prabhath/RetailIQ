# RetailIQ — Business Analytics Dashboard

RetailIQ is a data analytics project that helps businesses understand their sales, profits, discounts, and customers through interactive charts and dashboards.

The project uses the Sample Superstore dataset and is built with Python and Streamlit.

## Live Demo

**Try the application:** https://venkataprabhath-retailiq.streamlit.app

## Features

- **Executive Overview:** View total sales, profit, profit margin, and order statistics.
- **Profitability Analysis:** Identify profitable and unprofitable products.
- **Discount Analysis:** Understand how different discount levels relate to sales and profit.
- **Customer Analytics:** Analyze customer purchases and identify top customers.
- **Decision Simulator:** Explore how hypothetical changes in sales and costs could affect profit.
- **Data Quality:** Check missing values, duplicate records, and data issues.

## Technologies Used

- Python
- Pandas
- Streamlit
- Plotly
- PostgreSQL (optional)
- SQL
- Pytest

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Venkata-Prabhath/RetailIQ.git
cd RetailIQ
```

### 2. Install the dependencies

Create a virtual environment and install the required packages.

```bash
python -m venv .venv
```

On Windows:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Add the dataset

Download the [Sample Superstore dataset from Kaggle](https://www.kaggle.com/datasets/vivek468/superstore-dataset-final).

Place the CSV file in this location:

`data/raw/Sample - Superstore.csv`

You can also upload a compatible CSV file directly through the application.

### 4. Run the application

```bash
streamlit run app.py
```

Open the local URL displayed in your terminal to use the dashboard.

## Project Structure

```text
RetailIQ/
├── app.py                 # Main Streamlit application
├── data/
│   └── raw/               # Place the dataset here
├── src/
│   ├── data/               # Data loading and cleaning
│   ├── analytics/          # Metrics and calculations
│   └── database/           # Optional database operations
├── sql/                    # SQL analytics queries
├── tests/                  # Automated tests
├── requirements.txt        # Python dependencies
└── README.md               # Project documentation
```

## SQL Analysis

The project also includes SQL queries that answer business questions using techniques such as:

- GROUP BY and aggregate functions
- CASE statements
- Common Table Expressions (CTEs)
- Date-based analysis
- Window functions

## Run Tests

Run the following command to execute the automated tests:

```bash
pytest
```

## Notes

- The dataset is not included in this repository. Download it separately and check its license and usage terms.
- PostgreSQL is optional. The dashboard can run directly from a CSV file.
- The decision simulator provides hypothetical estimates, not guaranteed business forecasts.
- The analysis uses the profit values available in the dataset.

## Project Goal

The goal of RetailIQ is to demonstrate practical skills in data cleaning, exploratory data analysis, SQL, business analytics, data visualization, and interactive dashboard development.
