import numpy as np
import pandas as pd

def kpis(df):
    sales = float(df.sales.sum()) if len(df) else 0.0
    profit = float(df.profit.sum()) if len(df) else 0.0
    orders = int(df.order_id.nunique()) if "order_id" in df else int(len(df))
    return {"sales": sales, "profit": profit, "margin": profit / sales if sales else np.nan,
            "orders": orders, "aov": sales / orders if orders else np.nan}

def group_summary(df, by):
    cols = [c for c in by if c in df]
    if not cols: return pd.DataFrame()
    result = df.groupby(cols, dropna=False, observed=False).agg(sales=("sales", "sum"), profit=("profit", "sum"), rows=("profit", "size"))
    if "order_id" in df: result["orders"] = df.groupby(cols, dropna=False, observed=False).order_id.nunique()
    result["margin"] = result.profit.div(result.sales.where(result.sales.ne(0)))
    return result.reset_index()

def monthly_trend(df):
    data = df.dropna(subset=["order_date"]).copy()
    if data.empty: return pd.DataFrame(columns=["month", "sales", "profit"])
    return data.set_index("order_date").resample("MS").agg(sales=("sales", "sum"), profit=("profit", "sum")).reset_index(names="month")

def period_comparison(df, start, end):
    """Compare [start, end] with the immediately preceding equal-length window."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    days = (end.normalize() - start.normalize()).days + 1
    current = df[df.order_date.between(start, end)]
    previous_start, previous_end = start - pd.Timedelta(days=days), start - pd.Timedelta(days=1)
    previous = df[df.order_date.between(previous_start, previous_end)]
    now, before = kpis(current), kpis(previous)
    result = {}
    for key in ("sales", "profit", "orders"):
        absolute = now[key] - before[key]
        result[key] = {"current": now[key], "previous": before[key], "absolute_change": absolute,
                       "percentage_change": absolute / abs(before[key]) if before[key] != 0 else np.nan}
    return {"current_start": start.date(), "current_end": end.date(), "previous_start": previous_start.date(),
            "previous_end": previous_end.date(), "metrics": result}

def simulate(base, sales_change_pct=0, discount_change_pp=0, cost_change_pct=0):
    # Transparent scenario: sales shift applies to observed revenue; recorded profit shifts with revenue.
    # Discount and cost effects require unavailable price elasticity/cost model; they are sensitivity assumptions.
    sales_factor = 1 + sales_change_pct / 100
    baseline_sales, baseline_profit = base["sales"], base["profit"]
    scenario_sales = baseline_sales * sales_factor
    # No implied demand response to discounts; estimate profit adjustment against the explicit simple cost proxy.
    scenario_profit = baseline_profit * sales_factor - baseline_sales * (discount_change_pp / 100)
    scenario_profit *= 1 - cost_change_pct / 100
    return {"baseline_sales": baseline_sales, "baseline_profit": baseline_profit,
            "scenario_sales": scenario_sales, "scenario_profit": scenario_profit,
            "scenario_margin": scenario_profit / scenario_sales if scenario_sales else np.nan}
