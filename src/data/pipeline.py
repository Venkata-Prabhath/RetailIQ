from __future__ import annotations

import re
from pathlib import Path
from io import BytesIO
from urllib.request import Request, urlopen
from urllib.parse import urlparse
import pandas as pd
import numpy as np
import hashlib

ALIASES = {
    "source_row_id": ["row id", "row_id"], "order_id": ["order id", "order_id"], "order_date": ["order date", "order_date"],
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
    dates = pd.to_datetime(frame["order_date"], errors="coerce", format="mixed") if "order_date" in frame else pd.Series(dtype="datetime64[ns]")
    return {"rows": int(len(frame)), "columns": int(len(frame.columns)), "duplicates": int(frame.duplicated().sum()),
            "missing": {str(k): int(v) for k, v in frame.isna().sum().items()},
            "date_start": str(dates.min().date()) if dates.notna().any() else None,
            "date_end": str(dates.max().date()) if dates.notna().any() else None}

def prepare_data(frame: pd.DataFrame, column_mapping: dict[str, str] | None = None) -> tuple[pd.DataFrame, dict]:
    original = frame.copy(deep=True)
    if column_mapping is None:
        # Automatically map only high-confidence local schema matches. The UI
        # exposes inferred candidates for review when required roles are unclear.
        from src.data.schema import infer_schema, apply_schema_mapping
        inferred=infer_schema(frame)
        column_mapping={field:entry["source"] for field,entry in inferred["suggestions"].items() if entry.get("source")}
        out = apply_schema_mapping(frame, column_mapping)
    else:
        from src.data.schema import apply_schema_mapping
        out = apply_schema_mapping(frame, column_mapping)
    missing = sorted(REQUIRED - set(out.columns))
    if missing:
        raise ValueError("Required columns unavailable: " + ", ".join(missing) + ". Expected date, sales/revenue, and profit fields. Review or set column_mapping for unfamiliar source headings.")
    before = quality_summary(out)
    out["order_date"] = pd.to_datetime(out.order_date, errors="coerce", format="mixed")
    if "ship_date" in out: out["ship_date"] = pd.to_datetime(out.ship_date, errors="coerce", format="mixed")
    numeric_failures = {}
    for col in NUMERIC:
        if col in out:
            original_values = out[col].copy()
            out[col] = pd.to_numeric(out[col], errors="coerce")
            numeric_failures[col] = int((original_values.notna() & out[col].isna()).sum())
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
    # A source_row_id is a defensible key when supplied (as in Sample Superstore).
    # Otherwise fingerprint normalized source values and occurrence number, so
    # identical rows retain multiplicity while reruns remain idempotent.
    if "source_row_id" in out and out.source_row_id.notna().all() and out.source_row_id.is_unique:
        out["record_key"] = "source:" + out.source_row_id.astype(str)
        key_method = "source_row_id"
    else:
        source = out.drop(columns=[c for c in ["record_key"] if c in out], errors="ignore")
        if len(source):
            canonical = source.astype("string").fillna("<NULL>").agg("|".join, axis=1)
            fingerprints = canonical.map(lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest())
        else:
            fingerprints = pd.Series(index=out.index, dtype="object")
        occurrence = fingerprints.groupby(fingerprints, sort=False).cumcount()
        out["record_key"] = fingerprints + ":" + occurrence.astype(str)
        key_method = "sha256_normalized_row_plus_duplicate_occurrence"
    invalid_date = out.quality_invalid_date
    invalid_numeric = pd.Series(False, index=out.index)
    for col in ["sales", "profit"]:
        if col not in out:
            invalid_numeric |= True
        else:
            invalid_numeric |= out[col].isna()
    out["quality_rejected"] = invalid_date | invalid_numeric
    return out, {"before": before, "after": quality_summary(out), "source_rows": len(original),
                 "invalid_order_dates": int(out.quality_invalid_date.sum()), "negative_sales": int(out.quality_negative_sales.sum()),
                 "zero_sales": int(out.quality_zero_sales.sum()), "negative_profit": int(out.quality_negative_profit.sum()),
                 "numeric_conversion_failures": numeric_failures,
                 "valid_rows": int((~out.quality_rejected).sum()), "rejected_rows": int(out.quality_rejected.sum()),
                 "duplicate_rows": int(out.duplicated(subset=[c for c in out.columns if not c.startswith("quality_") and c not in {"record_key", "year", "month", "year_month", "profit_margin", "discount_band"}], keep="first").sum()),
                 "validation_failures": int(out.quality_rejected.sum()), "key_method": key_method,
                 "cleaning_rules": ["Preserve source values and negative-profit transactions.", "Unparseable dates and required numeric measures are quarantined from analytics, never deleted.", "Exact duplicates are retained and keyed by occurrence; repeated ingestion is idempotent.", "Overall margin is total profit divided by total sales."]}

def load_csv(path) -> tuple[pd.DataFrame, dict]:
    try:
        raw = pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        # The supplied Superstore export contains cp1252 punctuation in product names.
        raw = pd.read_csv(path, encoding="cp1252")
    return prepare_data(raw)

def _read_csv_bytes(content: bytes) -> pd.DataFrame:
    try:
        return pd.read_csv(BytesIO(content), encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(BytesIO(content), encoding="cp1252")

def load_csv_url(url: str) -> tuple[pd.DataFrame, dict]:
    """Load CSV from a stable HTTPS URL configured by the app owner."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("SUPERSTORE_CSV_URL must be a complete HTTPS URL.")
    request = Request(url, headers={"User-Agent": "RetailIQ/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            content = response.read()
    except Exception as exc:
        raise RuntimeError(f"Could not retrieve the configured dataset source: {exc}") from exc
    try:
        return prepare_data(_read_csv_bytes(content))
    except Exception as exc:
        raise ValueError(f"The configured HTTPS source did not return a valid Superstore CSV: {exc}") from exc

def local_dataset_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "raw" / "Sample - Superstore.csv"
