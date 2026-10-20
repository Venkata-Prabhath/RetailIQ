from __future__ import annotations

import re
from pathlib import Path
import pandas as pd
import numpy as np

ALIASES = {
    "order_id": ["order id", "order_id"], "order_date": ["order date", "order_date"],
    "ship_date": ["ship date", "ship_date"], "ship_mode": ["ship mode", "ship_mode"],
    "customer_id": ["customer id", "customer_id"], "customer_name": ["customer name", "customer_name"],
    "segment": ["segment"], "country": ["country"], "city": ["city"], "state": ["state"],
    "postal_code": ["postal code", "postal_code"], "region": ["region"], "product_id": ["product id", "product_id"],
    "category": ["category"], "sub_category": ["sub-category", "sub category", "sub_category"],
    "product_name": ["product name", "product_name"], "sales": ["sales"], "quantity": ["quantity"],
    "discount": ["discount"], "profit": ["profit"],
}
REQUIRED = {"order_date", "sales", "profit"}
NUMERIC = ["sales", "profit", "discount", "quantity"]

def normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    source = {re.sub(r"[^a-z0-9]+", " ", str(c).lower()).strip(): c for c in frame.columns}
    mapping = {}
    for target, names in ALIASES.items():
        for name in names:
            if name in source:
                mapping[source[name]] = target
                break
    return frame.rename(columns=mapping)

def quality_summary(frame: pd.DataFrame) -> dict:
    dates = pd.to_datetime(frame["order_date"], errors="coerce") if "order_date" in frame else pd.Series(dtype="datetime64[ns]")
    return {"rows": int(len(frame)), "columns": int(len(frame.columns)), "duplicates": int(frame.duplicated().sum()),
            "missing": {str(k): int(v) for k, v in frame.isna().sum().items()},
            "date_start": str(dates.min().date()) if dates.notna().any() else None,
            "date_end": str(dates.max().date()) if dates.notna().any() else None}

def prepare_data(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    original = frame.copy(deep=True)
    out = normalize_columns(frame.copy())
    missing = sorted(REQUIRED - set(out.columns))
    if missing:
        raise ValueError("Required columns unavailable: " + ", ".join(missing) + ". Expected at least Order Date, Sales, and Profit.")
    before = quality_summary(out)
    out["order_date"] = pd.to_datetime(out.order_date, errors="coerce")
    if "ship_date" in out: out["ship_date"] = pd.to_datetime(out.ship_date, errors="coerce")
    for col in NUMERIC:
        if col in out: out[col] = pd.to_numeric(out[col], errors="coerce")
    out["year"] = out.order_date.dt.year
    out["month"] = out.order_date.dt.month
    out["year_month"] = out.order_date.dt.to_period("M").astype("string")
    sales = out.sales.replace(0, np.nan)
    out["profit_margin"] = out.profit / sales
    if "discount" in out:
        out["discount_band"] = pd.cut(out.discount, [-np.inf, 0, .1, .2, .3, .5, np.inf], labels=["0%", "0–10%", "10–20%", "20–30%", "30–50%", "50%+"])
    out["quality_invalid_date"] = out.order_date.isna()
    out["quality_negative_sales"] = out.sales < 0
    out["quality_zero_sales"] = out.sales == 0
    out["quality_negative_profit"] = out.profit < 0
    return out, {"before": before, "after": quality_summary(out), "source_rows": len(original),
                 "invalid_order_dates": int(out.quality_invalid_date.sum()), "negative_sales": int(out.quality_negative_sales.sum()),
                 "zero_sales": int(out.quality_zero_sales.sum()), "negative_profit": int(out.quality_negative_profit.sum()),
                 "cleaning_rules": ["Preserve source rows and negative-profit transactions.", "Parse dates and numeric measures safely; invalid values become missing.", "Duplicate rows are reported, not removed automatically.", "Overall margin is total profit divided by total sales."]}

def load_csv(path) -> tuple[pd.DataFrame, dict]:
    try:
        raw = pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        # The supplied Superstore export contains cp1252 punctuation in product names.
        raw = pd.read_csv(path, encoding="cp1252")
    return prepare_data(raw)

def local_dataset_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "raw" / "Sample - Superstore.csv"
