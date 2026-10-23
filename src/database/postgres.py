"""PostgreSQL schema and idempotent persistence for RetailIQ batch runs."""
import os
import pandas as pd
from sqlalchemy import create_engine, text

def engine_from_env():
    url = os.getenv("DATABASE_URL")
    if not url: raise RuntimeError("PostgreSQL is not configured. Set DATABASE_URL, or use CSV mode.")
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return create_engine(url, pool_pre_ping=True, future=True)

def initialize_schema(engine=None):
    engine = engine or engine_from_env()
    statements = [
      "CREATE TABLE IF NOT EXISTS retail_transactions (record_key TEXT PRIMARY KEY, order_id TEXT, order_date DATE, ship_date DATE, ship_mode TEXT, customer_id TEXT, product_id TEXT, product_name TEXT, region TEXT, segment TEXT, category TEXT, sub_category TEXT, sales DOUBLE PRECISION, profit DOUBLE PRECISION, quantity DOUBLE PRECISION, discount DOUBLE PRECISION, payload JSONB NOT NULL)",
      "ALTER TABLE retail_transactions ADD COLUMN IF NOT EXISTS ship_mode TEXT",
      "ALTER TABLE retail_transactions ADD COLUMN IF NOT EXISTS segment TEXT",
      "CREATE INDEX IF NOT EXISTS ix_retail_transactions_order_date ON retail_transactions(order_date)",
      "CREATE INDEX IF NOT EXISTS ix_retail_transactions_product ON retail_transactions(product_id)",
      "CREATE TABLE IF NOT EXISTS pipeline_runs (run_id TEXT PRIMARY KEY, started_at TIMESTAMPTZ NOT NULL, finished_at TIMESTAMPTZ, status TEXT NOT NULL, source TEXT NOT NULL, source_fingerprint TEXT NOT NULL, source_rows INTEGER NOT NULL, valid_rows INTEGER NOT NULL, rejected_rows INTEGER NOT NULL, duplicate_rows INTEGER NOT NULL, summary JSONB NOT NULL)",
      "CREATE TABLE IF NOT EXISTS data_quality_results (run_id TEXT PRIMARY KEY REFERENCES pipeline_runs(run_id), result JSONB NOT NULL)",
      "CREATE TABLE IF NOT EXISTS kpi_snapshots (run_id TEXT PRIMARY KEY REFERENCES pipeline_runs(run_id), reporting_start DATE, reporting_end DATE, sales DOUBLE PRECISION, profit DOUBLE PRECISION, margin DOUBLE PRECISION, orders INTEGER, aov DOUBLE PRECISION)"
    ]
    with engine.begin() as conn:
        for statement in statements: conn.execute(text(statement))
    return engine

def persist_run(frame, quality, summary, source_fingerprint, run_id, *, engine=None, started_at=None):
    import json
    from datetime import datetime, timezone
    engine = initialize_schema(engine)
    started_at = started_at or datetime.now(timezone.utc)
    cols = ["record_key","order_id","order_date","ship_date","ship_mode","customer_id","product_id","product_name","region","segment","category","sub_category","sales","profit","quantity","discount"]
    with engine.begin() as conn:
        exists = conn.execute(text("SELECT run_id FROM pipeline_runs WHERE source_fingerprint=:fp AND status='success'"), {"fp":source_fingerprint}).first()
        if exists:
            conn.execute(text("INSERT INTO pipeline_runs(run_id,started_at,finished_at,status,source,source_fingerprint,source_rows,valid_rows,rejected_rows,duplicate_rows,summary) VALUES (:id,:started,now(),'skipped',:source,:fp,:source_rows,:valid,:rejected,:duplicates,CAST(:summary AS JSONB))"),
              {"id":run_id,"started":started_at,"source":summary["source"],"fp":source_fingerprint,"source_rows":quality["source_rows"],"valid":quality["valid_rows"],"rejected":quality["rejected_rows"],"duplicates":quality["duplicate_rows"],"summary":json.dumps({**summary,"skip_reason":"source_fingerprint_already_processed","prior_run_id":exists[0]},default=str)})
            return {"skipped":True,"reason":"source_fingerprint_already_processed","run_id":exists[0]}
        conn.execute(text("INSERT INTO pipeline_runs(run_id,started_at,status,source,source_fingerprint,source_rows,valid_rows,rejected_rows,duplicate_rows,summary) VALUES (:id,:started,'running',:source,:fp,:source_rows,:valid,:rejected,:duplicates,CAST(:summary AS JSONB))"),
          {"id":run_id,"started":started_at,"source":summary["source"],"fp":source_fingerprint,"source_rows":quality["source_rows"],"valid":quality["valid_rows"],"rejected":quality["rejected_rows"],"duplicates":quality["duplicate_rows"],"summary":json.dumps(summary,default=str)})
        records=[]
        for _, row in frame[~frame.quality_rejected].iterrows():
            data={c:(None if c not in row or pd.isna(row[c]) else row[c]) for c in cols}
            data["record_key"]=str(row.record_key)
            data["payload"]=json.dumps({k:(None if pd.isna(v) else v) for k,v in row.to_dict().items()},default=str)
            records.append(data)
        if records:
            conn.execute(text("""INSERT INTO retail_transactions(record_key,order_id,order_date,ship_date,ship_mode,customer_id,product_id,product_name,region,segment,category,sub_category,sales,profit,quantity,discount,payload)
              VALUES (:record_key,:order_id,:order_date,:ship_date,:ship_mode,:customer_id,:product_id,:product_name,:region,:segment,:category,:sub_category,:sales,:profit,:quantity,:discount,CAST(:payload AS JSONB))
              ON CONFLICT(record_key) DO UPDATE SET order_id=EXCLUDED.order_id,order_date=EXCLUDED.order_date,ship_date=EXCLUDED.ship_date,ship_mode=EXCLUDED.ship_mode,customer_id=EXCLUDED.customer_id,product_id=EXCLUDED.product_id,product_name=EXCLUDED.product_name,region=EXCLUDED.region,segment=EXCLUDED.segment,category=EXCLUDED.category,sub_category=EXCLUDED.sub_category,sales=EXCLUDED.sales,profit=EXCLUDED.profit,quantity=EXCLUDED.quantity,discount=EXCLUDED.discount,payload=EXCLUDED.payload"""),records)
        conn.execute(text("INSERT INTO data_quality_results(run_id,result) VALUES (:id,CAST(:result AS JSONB))"),{"id":run_id,"result":json.dumps(quality,default=str)})
        from src.analytics.metrics import kpis
        valid=frame[~frame.quality_rejected]
        m=kpis(valid)
        d=valid.order_date.dropna()
        conn.execute(text("INSERT INTO kpi_snapshots(run_id,reporting_start,reporting_end,sales,profit,margin,orders,aov) VALUES (:id,:start,:end,:sales,:profit,:margin,:orders,:aov)"),{"id":run_id,"start":d.min().date() if len(d) else None,"end":d.max().date() if len(d) else None,**m})
        conn.execute(text("UPDATE pipeline_runs SET finished_at=now(),status='success' WHERE run_id=:id"),{"id":run_id})
    return {"skipped":False,"run_id":run_id,"loaded_rows":quality["valid_rows"]}

def record_failed_run(run_id, source, error, *, started_at=None):
    """Best-effort durable failure record, including failures before ingestion."""
    import hashlib, json
    from datetime import datetime, timezone
    engine=initialize_schema()
    started_at=started_at or datetime.now(timezone.utc)
    fingerprint=hashlib.sha256(str(source).encode("utf-8")).hexdigest()
    with engine.begin() as conn:
        updated=conn.execute(text("UPDATE pipeline_runs SET finished_at=now(),status='failed',summary=CAST(:summary AS JSONB) WHERE run_id=:id"),{"id":run_id,"summary":json.dumps({"source":str(source),"status":"failed","error":str(error)[:1000]})})
        if not updated.rowcount:
            conn.execute(text("INSERT INTO pipeline_runs(run_id,started_at,finished_at,status,source,source_fingerprint,source_rows,valid_rows,rejected_rows,duplicate_rows,summary) VALUES (:id,:started,now(),'failed',:source,:fp,0,0,0,0,CAST(:summary AS JSONB))"),
              {"id":run_id,"started":started_at,"source":str(source),"fp":fingerprint,"summary":json.dumps({"source":str(source),"status":"failed","error":str(error)[:1000]})})

def query(sql, params=None):
    with engine_from_env().connect() as conn: return pd.read_sql(text(sql), conn, params=params or {})
