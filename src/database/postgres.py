import os
import pandas as pd
from sqlalchemy import create_engine, text

def engine_from_env():
    url = os.getenv("DATABASE_URL")
    if not url: raise RuntimeError("PostgreSQL is not configured. Set DATABASE_URL, or use CSV mode.")
    return create_engine(url, pool_pre_ping=True)

def load_table(frame: pd.DataFrame, table="superstore", if_exists="replace"):
    if if_exists not in {"replace", "append", "fail"}: raise ValueError("if_exists must be replace, append, or fail")
    frame.to_sql(table, engine_from_env(), if_exists=if_exists, index=False, chunksize=1000, method="multi")

def query(sql, params=None):
    with engine_from_env().connect() as conn: return pd.read_sql(text(sql), conn, params=params or {})
