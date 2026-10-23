"""Local, explainable column inference for unfamiliar retail CSV schemas."""
from __future__ import annotations
import re
import pandas as pd
from src.data.pipeline import ALIASES, normalize_columns

REQUIRED = {"order_date", "sales", "profit"}
SYNONYMS = {
 "order_date": ["date", "order date", "purchase date", "transaction date", "invoice date", "sale date", "created at", "timestamp", "purchased on"],
 "ship_date": ["ship date", "shipping date", "delivery date", "fulfilled date"],
 "order_id": ["order id", "order number", "transaction id", "transaction number", "invoice id", "receipt number", "ticket id"],
 "customer_id": ["customer id", "client id", "buyer id", "account id", "customer number"],
 "customer_name": ["customer name", "client name", "buyer name"],
 "product_id": ["product id", "sku", "item code", "product code", "stock keeping unit"],
 "product_name": ["product name", "item name", "product", "item", "description", "product description"],
 "category": ["category", "department", "product category", "merchandise group"],
 "sub_category": ["sub category", "subcategory", "product type", "sub department"],
 "region": ["region", "territory", "sales area", "market area"],
 "segment": ["segment", "customer segment", "channel"],
 "sales": ["sales", "revenue", "gross revenue", "net revenue", "sales amount", "total sales", "line total", "net sales", "total amount", "amount", "extended price"],
 "profit": ["profit", "net profit", "gross profit", "earnings", "net earnings", "contribution profit"],
 "quantity": ["quantity", "qty", "units sold", "unit count", "items sold"],
 "discount": ["discount", "discount rate", "markdown", "discount percent"],
 "ship_mode": ["ship mode", "shipping method", "delivery method", "fulfillment method"],
 "country": ["country"], "state": ["state", "province"], "city": ["city", "town"],
 "postal_code": ["postal code", "zip code", "postcode"]
}

def _words(value): return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()

def _score_header(column, field):
    name=_words(column)
    synonyms=SYNONYMS.get(field,[field.replace("_"," ")])
    exact={_words(x) for x in synonyms}
    if name in exact: return 0.98, "column name matches a known synonym"
    words=set(name.split())
    for synonym in exact:
        sw=set(synonym.split())
        if sw and sw.issubset(words): return 0.86, "column name contains a known field phrase"
    # Strong semantic anchors for headings with extra business-system prefixes.
    anchors={"order_date":{"date","purchase","transaction","invoice","ordered"},
      "sales":{"sales","revenue","amount","total","price"},
      "profit":{"profit","earnings","income"},
      "order_id":{"order","transaction","invoice","receipt","ticket"},
      "customer_id":{"customer","client","buyer"},"product_id":{"sku","product","item"}}
    if field in anchors and words.intersection(anchors[field]):
        if field=="profit" and "margin" in words: return 0.25,"profit-like name also contains ambiguous margin wording"
        if field=="sales" and words.intersection({"cost","profit","discount","quantity","qty","tax"}): return 0.20,"numeric measure name conflicts with sales"
        if field=="order_date" and not words.intersection({"date","time","at","on"}): return 0.20,"date-related entity but not clearly a date field"
        return 0.68,"column name has a related business term"
    return 0.0,"no useful name match"

def infer_schema(frame: pd.DataFrame) -> dict:
    """Suggest canonical fields from headers and value profiles without sending data away."""
    if not isinstance(frame,pd.DataFrame): raise TypeError("Expected a pandas DataFrame.")
    suggestions={}; profiles={}; used=set()
    # Existing known aliases are definitive suggestions, preserving current behavior.
    normalized=normalize_columns(frame.copy())
    for field in ALIASES:
        if field in normalized.columns:
            positions=[i for i,c in enumerate(normalized.columns) if c==field]
            pos=positions[0]
            suggestions[field]={"source":str(frame.columns[pos]),"confidence":0.99,"reason":"recognized existing RetailIQ alias"}
            used.add(pos)
    for pos,column in enumerate(frame.columns):
        values=frame.iloc[:,pos]
        sample=values.dropna().head(100)
        date_ratio=float(pd.to_datetime(sample,errors="coerce",format="mixed").notna().mean()) if len(sample) else 0.0
        numeric_ratio=float(pd.to_numeric(sample,errors="coerce").notna().mean()) if len(sample) else 0.0
        profiles[str(column)]={"dtype":str(values.dtype),"non_null":int(values.notna().sum()),"unique":int(values.nunique(dropna=True)),
          "sample_values":[str(v)[:80] for v in sample.head(3).tolist()],"date_like":date_ratio>=0.8,"numeric_like":numeric_ratio>=0.8}
    # Independent ranked candidates; only confidently distinct headers auto-map.
    for field in ALIASES:
        if field in suggestions: continue
        candidates=[]
        for pos,column in enumerate(frame.columns):
            if pos in used: continue
            score,reason=_score_header(column,field)
            prof=profiles[str(column)]
            if field in {"order_date","ship_date"}:
                if prof["date_like"]: score=max(score,0.72 if field=="order_date" else 0.35); reason="sample values parse consistently as dates"
                elif score>=0.65: score=0.30; reason="name suggests a date but sample values do not parse consistently"
            elif field in {"sales","profit","quantity","discount","postal_code"}:
                if prof["numeric_like"] and score>0: score=min(0.99,score+0.08)
                elif score>=0.65: score=0.30; reason="name suggests a numeric field but sample values are not mostly numeric"
            if score: candidates.append((score,pos,str(column),reason))
        candidates.sort(reverse=True)
        if not candidates: continue
        best=candidates[0]
        margin=best[0]-(candidates[1][0] if len(candidates)>1 else 0)
        confidence=best[0] if margin>=0.12 else min(best[0],0.65)
        suggestions[field]={"source":best[2] if confidence>=0.78 else None,"candidate":best[2],"confidence":round(confidence,2),
            "reason":best[3] if confidence>=0.78 else "ambiguous; review the candidate before analysis"}
        if suggestions[field]["source"]: used.add(best[1])
    missing=[field for field in sorted(REQUIRED) if field not in suggestions or not suggestions[field].get("source")]
    return {"suggestions":suggestions,"profiles":profiles,"required_missing":missing,"columns":[str(c) for c in frame.columns]}

def apply_schema_mapping(frame: pd.DataFrame, mapping: dict[str,str] | None=None) -> pd.DataFrame:
    """Rename selected source headers to canonical names before regular alias normalization."""
    if not mapping: return frame.copy()
    mapping={str(target):str(source) for target,source in mapping.items() if source not in (None,"")}
    if len(set(mapping.values())) != len(mapping): raise ValueError("A source column can only map to one RetailIQ field.")
    missing=[source for source in mapping.values() if source not in frame.columns]
    if missing: raise ValueError("Mapped source columns were not found: "+", ".join(missing))
    out=frame.copy()
    rename={}
    for target,source in mapping.items():
        if target not in ALIASES: raise ValueError(f"Unknown RetailIQ field: {target}")
        # Explicit user selections take precedence over alternate known aliases.
        alias_names={_words(name) for name in ALIASES[target]}
        for column in list(out.columns):
            if column!=source and _words(column) in alias_names: out=out.drop(columns=[column])
        rename[source]=target
    out=out.rename(columns=rename)
    out=normalize_columns(out)
    duplicated=out.columns[out.columns.duplicated()].tolist()
    if duplicated: raise ValueError("Multiple source columns map to the same field: "+", ".join(map(str,duplicated)))
    return out
