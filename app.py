from pathlib import Path
import sys
import pandas as pd
import streamlit as st
import plotly.express as px
from streamlit.errors import StreamlitSecretNotFoundError

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src.data.pipeline import load_csv, load_csv_url, prepare_data, local_dataset_path
from src.analytics.metrics import kpis, group_summary, monthly_trend, simulate

st.set_page_config(page_title="RetailIQ | Business Analytics", layout="wide", initial_sidebar_state="expanded")
st.markdown("<style>.block-container{padding-top:1.35rem;max-width:1440px}[data-testid=stMetric]{background:#fff;border:1px solid #e4e9f0;padding:12px 14px;border-radius:8px}[data-testid=stSidebar]{background:#f7f9fc;border-right:1px solid #e7ebf1}h1,h2,h3{color:#14243a}</style>", unsafe_allow_html=True)
st.title("RetailIQ")
st.caption("Business profitability and decision intelligence")

@st.cache_data(show_spinner="Loading and validating data…")
def load_upload(data):
    try: raw = pd.read_csv(data, encoding="utf-8-sig")
    except UnicodeDecodeError:
        data.seek(0)
        raw = pd.read_csv(data, encoding="cp1252")
    return prepare_data(raw)

@st.cache_data(ttl=3600, show_spinner="Loading the configured hosted dataset…")
def load_hosted(source_url): return load_csv_url(source_url)

pages = ["Executive overview", "Profitability explorer", "Discount intelligence", "Customer analytics", "Decision simulator", "Data quality & methodology"]
with st.sidebar:
    st.subheader("RetailIQ")
    page = st.radio("Navigation", pages, label_visibility="collapsed")
    st.divider()
    upload = st.file_uploader("Upload Superstore CSV", type="csv")
    path = local_dataset_path()

try:
    if upload:
        df, quality = load_upload(upload)
    elif path.exists():
        df, quality = load_csv(path)
    else:
        try: source_url = st.secrets["SUPERSTORE_CSV_URL"]
        except (KeyError, StreamlitSecretNotFoundError): source_url = ""
        if not source_url:
            raise FileNotFoundError
        df, quality = load_hosted(source_url)
except FileNotFoundError:
    st.error(f"Dataset not found at `{path}` and no hosted source is configured. In Streamlit Community Cloud, open your app's Settings → Secrets and add `SUPERSTORE_CSV_URL = \"https://your-host/path/Sample%20-%20Superstore.csv\"` using a stable, permitted URL that returns the CSV file directly over HTTPS. Do not use a Kaggle page URL or a ZIP link. Locally, place the CSV at `{path}`.")
    st.stop()
except Exception as exc:
    st.error(f"Could not load the dataset: {exc}")
    st.stop()

with st.sidebar:
    st.caption(f"{len(df):,} loaded rows")
    lo, hi = df.order_date.min(), df.order_date.max()
    if pd.notna(lo) and pd.notna(hi):
        dates = st.date_input("Order date range", (lo.date(), hi.date()), min_value=lo.date(), max_value=hi.date())
        start, end = dates if isinstance(dates, tuple) and len(dates) == 2 else (lo.date(), hi.date())
    else: start = end = None
    filters = {}
    for col, label in [("region", "Region"), ("segment", "Segment"), ("category", "Category")]:
        if col in df:
            opts = sorted(df[col].dropna().astype(str).unique())
            filters[col] = st.multiselect(label, opts, default=opts)

filtered = df.copy()
if start is not None: filtered = filtered[filtered.order_date.dt.date.between(start, end)]
for col, vals in filters.items(): filtered = filtered[filtered[col].astype(str).isin(vals)] if vals else filtered.iloc[0:0]

def header(title, description): st.header(title); st.caption(description)
def money(v): return "—" if pd.isna(v) else f"${v:,.0f}"
def empty(): st.info("No rows match the current filters. Adjust the date range or selections in the sidebar.")

if page == "Executive overview":
    header("Executive overview", "Track sales, recorded profit, and performance across the selected period.")
    if filtered.empty: empty(); st.stop()
    m = kpis(filtered)
    cards = st.columns(5)
    vals = [("Sales", money(m["sales"])), ("Profit", money(m["profit"])), ("Profit margin", f"{m['margin']:.1%}" if pd.notna(m["margin"]) else "—"), ("Orders", f"{m['orders']:,}"), ("Average order value", money(m["aov"]))]
    for col, (label, value) in zip(cards, vals): col.metric(label, value)
    trend = monthly_trend(filtered)
    a,b = st.columns(2)
    with a: st.plotly_chart(px.line(trend,x="month",y="sales",title="Monthly sales",labels={"month":"Order month","sales":"Sales ($)"}),width="stretch")
    with b: st.plotly_chart(px.line(trend,x="month",y="profit",title="Monthly recorded profit",labels={"month":"Order month","profit":"Profit ($)"}),width="stretch")
    a,b = st.columns(2)
    if "region" in filtered:
        with a: st.plotly_chart(px.bar(group_summary(filtered,["region"]).sort_values("sales",ascending=False),x="region",y="sales",title="Sales by region",labels={"region":"Region","sales":"Sales ($)"}),width="stretch")
    if "category" in filtered:
        with b: st.plotly_chart(px.bar(group_summary(filtered,["category"]).sort_values("profit"),x="category",y="profit",title="Recorded profit by category",labels={"category":"Category","profit":"Profit ($)"}),width="stretch")
    with st.expander("Metric definitions"): st.write("Profit margin is total recorded profit divided by total sales. Orders counts distinct order IDs where available; otherwise it counts rows. Average order value is sales divided by order count.")

elif page == "Profitability explorer":
    header("Profitability explorer", "Compare recorded profit with revenue across product groups and products.")
    if filtered.empty: empty(); st.stop()
    dims = [c for c in ["category","sub_category"] if c in filtered]
    if dims: st.plotly_chart(px.bar(group_summary(filtered,dims).sort_values("profit"),x=dims[-1],y="profit",color=dims[0] if len(dims)>1 else None,title="Recorded profit by product group",labels={"profit":"Profit ($)"}),width="stretch")
    if "product_name" in filtered:
        products = group_summary(filtered,["product_name"]).sort_values("profit")
        st.subheader("Products by recorded profit"); st.dataframe(products,width="stretch",hide_index=True)
        st.download_button("Download product results",products.to_csv(index=False),"retailiq_products.csv","text/csv")
        st.caption(f"{int((products.profit < 0).sum()):,} products have negative cumulative recorded profit in this selection.")

elif page == "Discount intelligence":
    header("Discount intelligence", "Explore how observed discount bands relate to recorded sales and profit.")
    if "discount_band" not in filtered: st.info("Discount analysis is unavailable because the dataset has no discount field."); st.stop()
    if filtered.empty: empty(); st.stop()
    bands = group_summary(filtered,["discount_band"]); a,b = st.columns(2)
    with a: st.plotly_chart(px.bar(bands,x="discount_band",y="sales",title="Sales by discount band",labels={"discount_band":"Discount band","sales":"Sales ($)"}),width="stretch")
    with b: st.plotly_chart(px.bar(bands,x="discount_band",y="profit",title="Recorded profit by discount band",labels={"discount_band":"Discount band","profit":"Profit ($)"}),width="stretch")
    st.warning("These observational comparisons do not establish that discounts caused a profit change. Product mix, promotions, and other factors may affect both.")
    st.dataframe(bands,width="stretch",hide_index=True)

elif page == "Customer analytics":
    header("Customer analytics", "Review customer revenue, cumulative recorded profit, and repeat ordering where supported.")
    if "customer_id" not in filtered: st.info("Customer analysis is unavailable because the dataset has no customer identifier."); st.stop()
    if filtered.empty: empty(); st.stop()
    customers = group_summary(filtered,["customer_id"]); a,b = st.columns(2)
    with a: st.plotly_chart(px.bar(customers.nlargest(10,"sales").sort_values("sales"),x="sales",y="customer_id",orientation="h",title="Top customers by sales",labels={"sales":"Sales ($)","customer_id":"Customer"}),width="stretch")
    with b: st.plotly_chart(px.bar(customers.nsmallest(10,"profit").sort_values("profit"),x="profit",y="customer_id",orientation="h",title="Lowest cumulative recorded profit",labels={"profit":"Profit ($)","customer_id":"Customer"}),width="stretch")
    if "order_id" in filtered:
        counts = filtered.groupby("customer_id").order_id.nunique(); repeat = int((counts >= 2).sum())
        st.caption(f"Repeat customers (2+ distinct orders): {repeat:,} of {len(counts):,} ({repeat/len(counts):.1%}).")
    st.dataframe(customers.sort_values("sales",ascending=False),width="stretch",hide_index=True)
    st.download_button("Download customer results",customers.to_csv(index=False),"retailiq_customers.csv","text/csv")

elif page == "Decision simulator":
    header("Decision simulator", "Explore a transparent sensitivity scenario using the filtered baseline.")
    if filtered.empty: empty(); st.stop()
    baseline = kpis(filtered)
    with st.container(border=True):
        a,b = st.columns(2)
        with a: sales_pct = st.slider("Hypothetical sales change (%)",-50,50,0)
        with b: discount_pp = st.slider("Profit adjustment per discount change (percentage points)",-20,20,0)
        cost_pct = st.slider("Hypothetical profit cost adjustment (%)",-50,50,0)
    result = simulate(baseline,sales_pct,discount_pp,cost_pct)
    st.caption("Assumptions: sales change scales observed sales and profit; discount adjustment reduces profit by the selected percentage of baseline sales, with no demand response; cost adjustment changes resulting profit. This is a sensitivity estimate, not a forecast.")
    a,b = st.columns(2)
    with a: st.subheader("Baseline (observed)"); st.metric("Sales",money(result["baseline_sales"])); st.metric("Recorded profit",money(result["baseline_profit"]))
    with b: st.subheader("Scenario (modeled)"); st.metric("Sales",money(result["scenario_sales"])); st.metric("Estimated profit",money(result["scenario_profit"])); st.metric("Estimated margin",f"{result['scenario_margin']:.1%}" if pd.notna(result["scenario_margin"]) else "—")

else:
    header("Data quality & methodology", "Inspect source coverage, validation results, cleaning rules, and limitations.")
    st.write(f"**Rows loaded:** {quality['source_rows']:,} · **Exact duplicates:** {quality['before']['duplicates']:,} · **Invalid order dates:** {quality['invalid_order_dates']:,}")
    if quality["after"]["date_start"]: st.write(f"**Date coverage:** {quality['after']['date_start']} to {quality['after']['date_end']}")
    missing = pd.DataFrame({"Column":list(quality["before"]["missing"]),"Missing rows":list(quality["before"]["missing"].values())})
    st.subheader("Missing values"); st.dataframe(missing,width="stretch",hide_index=True)
    with st.expander("Cleaning rules and KPI definitions"):
        for rule in quality["cleaning_rules"]: st.write(rule)
        st.write("Margins use ratios of aggregated totals. Invalid dates and numeric values become missing. Negative profit is retained as a valid business outcome.")
    with st.expander("Data dictionary and limitations"):
        st.write("Common Sample Superstore labels map to normalized fields. Missing dimensions are excluded from related analysis. No cost model, stock data, or demand elasticity is assumed, so the app does not infer gross margin, inventory risk, discount causality, or discount-driven sales response.")
    st.subheader("Available fields"); st.write(", ".join(df.columns))
    st.download_button("Download filtered rows",filtered.to_csv(index=False),"retailiq_filtered.csv","text/csv")

