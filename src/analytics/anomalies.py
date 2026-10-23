from __future__ import annotations
import pandas as pd

def detect_anomalies(df, *, drop_pct=30.0, spike_pct=50.0, min_baseline=3, previous_quality=None, quality=None):
    """Explainable checks using prior monthly observations as the baseline."""
    alerts = []
    if df.empty or "order_date" not in df:
        return alerts
    data=df.dropna(subset=["order_date"]).copy()
    data["_month"] = data.order_date.dt.to_period("M").dt.to_timestamp()
    dimensions=[("month",None)]+[(dim,dim) for dim in ("region","category") if dim in data]
    for dimension, column in dimensions:
      members=[("all",data)] if column is None else [(str(name),group) for name,group in data.groupby(column,dropna=False)]
      for member, subset in members:
        monthly=subset.groupby("_month").agg(sales=("sales","sum"),profit=("profit","sum"))
        for metric in ("sales", "profit"):
          values=monthly[metric]
          for i in range(min_baseline,len(values)):
            baseline=float(values.iloc[max(0,i-min_baseline):i].mean()); observed=float(values.iloc[i])
            if baseline==0: continue
            pct=(observed-baseline)/abs(baseline)*100
            threshold=-drop_pct if pct<0 else spike_pct
            if pct<=-drop_pct or pct>=spike_pct:
                alerts.append({"metric": metric, "dimension": dimension, "group": f"{member} / {values.index[i].date()}",
                    "observed": observed, "baseline": baseline, "absolute_deviation": observed-baseline,
                    "percentage_deviation": pct, "rule": f"Prior {min_baseline}-month mean; {'drop' if pct < 0 else 'spike'} threshold {abs(threshold):g}%",
                    "severity": "high" if abs(pct) >= max(drop_pct, spike_pct)*2 else "medium",
                    "recommendation": "Review transaction mix, timing, and source data; this alert does not identify a cause."})
    if "product_name" in df:
        groups = df.groupby("product_name", dropna=False).agg(sales=("sales", "sum"), profit=("profit", "sum"))
        for name, row in groups[groups.profit < 0].iterrows():
            alerts.append({"metric":"profit", "dimension":"product", "group":str(name), "observed":float(row.profit),
                "baseline":0.0, "absolute_deviation":float(row.profit), "percentage_deviation":None,
                "rule":"Cumulative recorded profit below zero", "severity":"medium",
                "recommendation":"Review price, discount, and fulfillment records for this product."})
    if quality and previous_quality:
        current_rate=quality["rejected_rows"]/max(quality["source_rows"],1)
        previous_rate=previous_quality.get("rejected_rate",0)
        if current_rate>previous_rate and current_rate-previous_rate>=0.01:
            alerts.append({"metric":"rejected_row_rate","dimension":"pipeline_run","group":"latest run","observed":current_rate,"baseline":previous_rate,
              "absolute_deviation":current_rate-previous_rate,"percentage_deviation":(current_rate-previous_rate)/previous_rate*100 if previous_rate else None,
              "rule":"Rejected-row rate increased by at least 1 percentage point versus prior run","severity":"high" if current_rate-previous_rate>=0.05 else "medium",
              "recommendation":"Inspect recent validation failures and source changes."})
    return alerts
