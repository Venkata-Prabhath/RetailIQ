from pathlib import Path
import sys

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src.data.pipeline import load_csv, load_csv_url, prepare_data, local_dataset_path
from src.analytics.metrics import kpis, group_summary, monthly_trend, simulate

st.set_page_config(page_title="RetailIQ | Business Analytics", page_icon="â–¦", layout="wide", initial_sidebar_state="expanded")

appearance = st.sidebar.radio("Appearance", ["Light", "Dark"], horizontal=True, label_visibility="collapsed", key="appearance")
dark = appearance == "Dark"
theme = {
    "canvas": "#0b1220" if dark else "#f7f9fc",
    "surface": "#111c2e" if dark else "#ffffff",
    "ink": "#e6edf7" if dark else "#14243a",
    "muted": "#9aabc1" if dark else "#64748b",
    "line": "#26364d" if dark else "#e5eaf1",
    "grid": "#223148" if dark else "#edf1f5",
    "blue": "#72a7ff" if dark else "#2f6fed",
    "sidebar": "#0e1828" if dark else "#ffffff",
    "header": "rgba(11,18,32,.94)" if dark else "rgba(247,249,252,.92)",
}
st.markdown(f"""
<style>
:root {{ --ink:{theme['ink']}; --muted:{theme['muted']}; --line:{theme['line']}; --blue:{theme['blue']}; --canvas:{theme['canvas']}; }}
.stApp {{ background:radial-gradient(ellipse at 50% -20%, {'#1c3150' if dark else '#eaf1fc'} 0%, var(--canvas) 54%); color:var(--ink); }}
[data-testid="stHeader"] {{ background:{theme['header']}; }}
[data-testid="stSidebar"] {{ background:{theme['sidebar']}; border-right:1px solid var(--line); }}
[data-testid="stSidebar"] div[data-testid="stRadio"] > label {{ color:var(--muted); }}
.block-container {{ max-width:1440px; padding:1.55rem 2.2rem 3rem; }}
[data-testid="stSidebar"] > div:first-child {{ padding-top:1.25rem; }}
[data-testid="stSidebar"] [data-testid="stRadio"] label {{ font-weight:550; }}
h1,h2,h3,p,label {{ color:var(--ink); letter-spacing:-.015em; }}
h1 {{ font-size:2rem !important; font-weight:700 !important; margin-bottom:.15rem !important; }}
h2 {{ font-size:1.35rem !important; font-weight:650 !important; }}
h3 {{ font-size:1.08rem !important; font-weight:650 !important; }}
[data-testid="stMetric"] {{ background:{theme['surface']}; border:1px solid var(--line); border-radius:14px; padding:16px 18px; min-height:112px; box-shadow:0 8px 24px rgba(0,0,0,{'0.18' if dark else '0.035'}); transition:transform .18s ease,border-color .18s ease; }}
[data-testid="stMetric"]:hover {{ transform:translateY(-2px); border-color:var(--blue); }}
[data-testid="stMetricLabel"] {{ color:var(--muted); font-size:.84rem; font-weight:600; }}
[data-testid="stMetricValue"] {{ color:var(--ink); font-size:clamp(1.35rem,2vw,1.9rem); font-weight:700; white-space:nowrap; }}
[data-testid="stVerticalBlock"] > [data-testid="stPlotlyChart"] {{ background:{theme['surface']}; border:1px solid var(--line); border-radius:14px; padding:8px; box-shadow:0 8px 24px rgba(0,0,0,{'0.16' if dark else '0.025'}); }}
[data-testid="stDataFrame"] {{ border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
[data-testid="stFileUploader"] {{ border:1px dashed {theme['line']}; border-radius:10px; padding:8px; background:{theme['surface']}; }}
div[data-testid="stAlert"] {{ border-radius:10px; }}
.page-intro {{ color:var(--muted); margin:.1rem 0 1.35rem; font-size:.98rem; }}
.eyebrow {{ color:var(--blue); font-size:.73rem; text-transform:uppercase; letter-spacing:.11em; font-weight:700; margin:0 0 .25rem; }}
[data-baseweb="input"] > div,[data-baseweb="select"] > div,[data-testid="stDateInput"] input {{ background:{theme['surface']}; border-color:var(--line); }}
[data-testid="stCaptionContainer"] {{ color:var(--muted); }}
@media (max-width: 900px) {{ .block-container {{ padding:1.2rem 1rem 2rem; }} [data-testid="stMetric"] {{ padding:13px; }} }}
</style>
""", unsafe_allow_html=True)

@st.cache_data(show_spinner="Loading and validating dataâ€¦")
def load_upload(data):
    try:
        raw = pd.read_csv(data, encoding="utf-8-sig")
    except UnicodeDecodeError:
        data.seek(0)
        raw = pd.read_csv(data, encoding="cp1252")
    return prepare_data(raw)

@st.cache_data(ttl=3600, show_spinner="Loading the configured hosted datasetâ€¦")
def load_hosted(source_url):
    return load_csv_url(source_url)

PAGES = ["Executive overview", "Profitability explorer", "Discount intelligence", "Customer analytics", "Decision simulator", "Data quality & methodology"]

with st.sidebar:
    st.markdown("<div class='eyebrow'>Business intelligence</div>", unsafe_allow_html=True)
    st.markdown("## RetailIQ")
    st.caption("Sales Â· Profitability Â· Decisions")
    st.divider()
    page = st.radio("Workspace", PAGES, label_visibility="collapsed")
    st.divider()
    st.markdown("**Data source**")
    upload = st.file_uploader("Upload Superstore CSV", type="csv", help="Use a CSV with Order Date, Sales, and Profit columns.")
    path = local_dataset_path()

try:
    if upload:
        df, quality = load_upload(upload)
        source_label = upload.name
    elif path.exists():
        df, quality = load_csv(path)
        source_label = path.name
    else:
        try:
            source_url = st.secrets["SUPERSTORE_CSV_URL"]
        except (KeyError, StreamlitSecretNotFoundError):
            source_url = ""
        if not source_url:
            raise FileNotFoundError
        df, quality = load_hosted(source_url)
        source_label = "Hosted CSV"
except FileNotFoundError:
    st.error(f"Dataset not found at `{path}` and no hosted source is configured. In Streamlit Community Cloud, add `SUPERSTORE_CSV_URL = \"https://your-host/path/Sample%20-%20Superstore.csv\"` in app Secrets. Locally, place the CSV at `{path}`.")
    st.stop()
except Exception as exc:
    st.error(f"Could not load the dataset: {exc}")
    st.stop()

with st.sidebar:
    st.success(f"{len(df):,} rows loaded")
    st.caption(f"Source: {source_label}")
    lo, hi = df.order_date.min(), df.order_date.max()
    if pd.notna(lo) and pd.notna(hi):
        dates = st.date_input("Order date range", (lo.date(), hi.date()), min_value=lo.date(), max_value=hi.date())
        start, end = dates if isinstance(dates, tuple) and len(dates) == 2 else (lo.date(), hi.date())
    else:
        start = end = None
    filters = {}
    for col, label in [("region", "Region"), ("segment", "Segment"), ("category", "Category")]:
        if col in df:
            opts = sorted(df[col].dropna().astype(str).unique())
            filters[col] = st.multiselect(label, opts, default=opts, placeholder=f"All {label.lower()}s")

filtered = df.copy()
if start is not None:
    filtered = filtered[filtered.order_date.dt.date.between(start, end)]
for col, vals in filters.items():
    filtered = filtered[filtered[col].astype(str).isin(vals)] if vals else filtered.iloc[0:0]

def header(title, description):
    st.markdown("<div class='eyebrow'>RetailIQ analytics</div>", unsafe_allow_html=True)
    st.title(title)
    st.markdown(f"<div class='page-intro'>{description}</div>", unsafe_allow_html=True)

def compact_money(value):
    if pd.isna(value):
        return "â€”"
    sign = "âˆ’" if value < 0 else ""
    value = abs(float(value))
    if value >= 1_000_000:
        return f"{sign}${value / 1_000_000:.2f}M"
    if value >= 10_000:
        return f"{sign}${value / 1_000:.0f}K"
    if value >= 1_000:
        return f"{sign}${value / 1_000:.1f}K"
    return f"{sign}${value:,.0f}"

def money(value):
    return "â€”" if pd.isna(value) else f"{'âˆ’' if value < 0 else ''}${abs(value):,.2f}"

def empty():
    st.info("No rows match the current filters. Adjust the date range or selections in the sidebar.")

def polish(fig, height=350, currency_axes=()):
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white", height=height, margin=dict(l=18, r=18, t=58, b=18),
        paper_bgcolor=theme["surface"], plot_bgcolor=theme["surface"],
        font=dict(family="Arial, sans-serif", color=theme["ink"], size=12),
        title=dict(font=dict(size=16, color=theme["ink"]), x=0.02, xanchor="left"),
        colorway=[theme["blue"], "#62a0ff", "#34d399", "#fbbf24", "#a78bfa"],
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hoverlabel=dict(bgcolor="#14243a", font_color="#fff"),
    )
    fig.update_xaxes(showgrid=False, linecolor=theme["line"], tickfont=dict(color=theme["muted"]))
    fig.update_yaxes(showgrid=True, gridcolor=theme["grid"], zerolinecolor=theme["line"], tickfont=dict(color=theme["muted"]))
    for axis in currency_axes:
        getattr(fig.layout, f"{axis}axis").tickprefix = "$"
        getattr(fig.layout, f"{axis}axis").tickformat = ",.2s"
    fig.update_traces(hovertemplate=None, hoverlabel_namelength=-1)
    return fig

def chart(fig, height=350, currency_axes=()):
    st.plotly_chart(polish(fig, height, currency_axes), use_container_width=True, config={"displayModeBar": False, "responsive": True})

if page == "Executive overview":
    header("Executive overview", "A focused view of sales, recorded profit, and performance for the selected period.")
    if filtered.empty:
        empty(); st.stop()
    m = kpis(filtered)
    cards = st.columns(5, gap="medium")
    values = [("Sales", compact_money(m["sales"]), f"Full value: {money(m['sales'])}"), ("Recorded profit", compact_money(m["profit"]), f"Full value: {money(m['profit'])}"), ("Profit margin", f"{m['margin']:.1%}" if pd.notna(m["margin"]) else "â€”", "Total recorded profit divided by total sales"), ("Orders", f"{m['orders']:,}", "Distinct order IDs where available"), ("Average order value", compact_money(m["aov"]), f"Full value: {money(m['aov'])}")]
    for col, (label, value, help_text) in zip(cards, values):
        col.metric(label, value, help=help_text)
    st.write("")
    trend = monthly_trend(filtered)
    a, b = st.columns(2, gap="medium")
    with a:
        chart(px.line(trend, x="month", y="sales", title="Monthly sales", labels={"month":"Order month", "sales":"Sales"}, markers=True), currency_axes=("y",))
    with b:
        chart(px.line(trend, x="month", y="profit", title="Monthly recorded profit", labels={"month":"Order month", "profit":"Profit"}, markers=True), currency_axes=("y",))
    a, b = st.columns(2, gap="medium")
    if "region" in filtered:
        with a:
            chart(px.bar(group_summary(filtered,["region"]).sort_values("sales",ascending=False), x="region", y="sales", title="Sales by region", labels={"region":"Region", "sales":"Sales"}), currency_axes=("y",))
    if "category" in filtered:
        with b:
            chart(px.bar(group_summary(filtered,["category"]).sort_values("profit"), x="category", y="profit", title="Recorded profit by category", labels={"category":"Category", "profit":"Profit"}), currency_axes=("y",))
    if len(trend):
        peak = trend.loc[trend.sales.idxmax()]
        st.caption(f"Selected-period observation: {peak.month:%B %Y} has the highest monthly sales ({money(peak.sales)}).")
    with st.expander("Metric definitions"):
        st.write("Profit margin is total recorded profit divided by total sales. Orders counts distinct order IDs where available; otherwise it counts rows. Average order value is sales divided by order count.")

elif page == "Profitability explorer":
    header("Profitability explorer", "Compare recorded profit with revenue across product groups and products.")
    if filtered.empty:
        empty(); st.stop()
    dims = [c for c in ["category", "sub_category"] if c in filtered]
    if dims:
        chart(px.bar(group_summary(filtered,dims).sort_values("profit"), x=dims[-1], y="profit", color=dims[0] if len(dims)>1 else None, title="Recorded profit by product group", labels={"profit":"Profit", dims[-1]:dims[-1].replace("_"," ").title()}), currency_axes=("y",))
    if "product_name" in filtered:
        products = group_summary(filtered,["product_name"]).sort_values("profit")
        st.subheader("Products by recorded profit")
        st.dataframe(products, use_container_width=True, hide_index=True)
        st.download_button("Download product results", products.to_csv(index=False), "retailiq_products.csv", "text/csv")
        negative = int((products.profit < 0).sum())
        st.caption(f"{negative:,} of {len(products):,} products have negative cumulative recorded profit in this selection.")

elif page == "Discount intelligence":
    header("Discount intelligence", "Explore how observed discount bands relate to recorded sales and profit.")
    if "discount_band" not in filtered:
        st.info("Discount analysis is unavailable because the dataset has no discount field."); st.stop()
    if filtered.empty:
        empty(); st.stop()
    bands = group_summary(filtered,["discount_band"])
    a, b = st.columns(2, gap="medium")
    with a:
        chart(px.bar(bands,x="discount_band",y="sales",title="Sales by discount band",labels={"discount_band":"Discount band", "sales":"Sales"}), currency_axes=("y",))
    with b:
        chart(px.bar(bands,x="discount_band",y="profit",title="Recorded profit by discount band",labels={"discount_band":"Discount band", "profit":"Profit"}), currency_axes=("y",))
    st.caption(f"Observed range in this selection: {filtered.discount.min():.0%} to {filtered.discount.max():.0%} discount.")
    st.warning("These observational comparisons do not establish that discounts caused a profit change. Product mix, promotions, and other factors may affect both.")
    st.dataframe(bands, use_container_width=True, hide_index=True)

elif page == "Customer analytics":
    header("Customer analytics", "Review customer revenue, cumulative recorded profit, and repeat ordering where supported.")
    if "customer_id" not in filtered:
        st.info("Customer analysis is unavailable because the dataset has no customer identifier."); st.stop()
    if filtered.empty:
        empty(); st.stop()
    customers = group_summary(filtered,["customer_id"])
    a, b = st.columns(2, gap="medium")
    with a:
        chart(px.bar(customers.nlargest(10,"sales").sort_values("sales"), x="sales", y="customer_id", orientation="h", title="Top customers by sales", labels={"sales":"Sales", "customer_id":"Customer"}), currency_axes=("x",))
    with b:
        chart(px.bar(customers.nsmallest(10,"profit").sort_values("profit"), x="profit", y="customer_id", orientation="h", title="Lowest cumulative recorded profit", labels={"profit":"Profit", "customer_id":"Customer"}), currency_axes=("x",))
    if "order_id" in filtered:
        counts = filtered.groupby("customer_id").order_id.nunique()
        repeat = int((counts >= 2).sum())
        st.caption(f"Repeat customers (2+ distinct orders): {repeat:,} of {len(counts):,} ({repeat/len(counts):.1%}).")
    st.dataframe(customers.sort_values("sales",ascending=False), use_container_width=True, hide_index=True)
    st.download_button("Download customer results", customers.to_csv(index=False), "retailiq_customers.csv", "text/csv")

elif page == "Decision simulator":
    header("Decision simulator", "Explore a transparent sensitivity scenario using the filtered baseline.")
    if filtered.empty:
        empty(); st.stop()
    baseline = kpis(filtered)
    with st.container(border=True):
        a, b = st.columns(2)
        with a:
            sales_pct = st.slider("Hypothetical sales change (%)", -50, 50, 0)
        with b:
            discount_pp = st.slider("Profit adjustment per discount change (percentage points)", -20, 20, 0)
        cost_pct = st.slider("Hypothetical profit cost adjustment (%)", -50, 50, 0)
    result = simulate(baseline, sales_pct, discount_pp, cost_pct)
    st.caption("Assumptions: sales change scales observed sales and profit; discount adjustment reduces profit by the selected percentage of baseline sales, with no demand response; cost adjustment changes resulting profit. This is a sensitivity estimate, not a forecast.")
    a, b = st.columns(2, gap="medium")
    with a:
        st.subheader("Baseline (observed)")
        st.metric("Sales", compact_money(result["baseline_sales"]), help=f"Full value: {money(result['baseline_sales'])}")
        st.metric("Recorded profit", compact_money(result["baseline_profit"]), help=f"Full value: {money(result['baseline_profit'])}")
    with b:
        st.subheader("Scenario (modeled)")
        st.metric("Sales", compact_money(result["scenario_sales"]), help=f"Full value: {money(result['scenario_sales'])}")
        st.metric("Estimated profit", compact_money(result["scenario_profit"]), help=f"Full value: {money(result['scenario_profit'])}")
        st.metric("Estimated margin", f"{result['scenario_margin']:.1%}" if pd.notna(result["scenario_margin"]) else "â€”")

else:
    header("Data quality & methodology", "Inspect source coverage, validation results, cleaning rules, and analytical limitations.")
    st.subheader("Dataset snapshot")
    c1, c2, c3 = st.columns(3)
    c1.metric("Rows loaded", f"{quality['source_rows']:,}")
    c2.metric("Exact duplicates", f"{quality['before']['duplicates']:,}")
    c3.metric("Invalid order dates", f"{quality['invalid_order_dates']:,}")
    if quality["after"]["date_start"]:
        st.caption(f"Date coverage: {quality['after']['date_start']} to {quality['after']['date_end']}")
    missing = pd.DataFrame({"Column":list(quality["before"]["missing"]), "Missing rows":list(quality["before"]["missing"].values())})
    st.subheader("Missing values")
    st.dataframe(missing, use_container_width=True, hide_index=True)
    with st.expander("Cleaning rules and KPI definitions"):
        for rule in quality["cleaning_rules"]:
            st.write(rule)
        st.write("Margins use ratios of aggregated totals. Invalid dates and numeric values become missing. Negative profit is retained as a valid business outcome.")
    with st.expander("Data dictionary and limitations"):
        st.write("Common Sample Superstore labels map to normalized fields. Missing dimensions are excluded from related analysis. No cost model, stock data, or demand elasticity is assumed, so the app does not infer gross margin, inventory risk, discount causality, or discount-driven sales response.")
    st.subheader("Available fields")
    st.write(", ".join(df.columns))
    st.download_button("Download filtered rows", filtered.to_csv(index=False), "retailiq_filtered.csv", "text/csv")
