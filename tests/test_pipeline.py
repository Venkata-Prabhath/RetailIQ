import pandas as pd
import pytest
from zipfile import ZipFile
from io import BytesIO
from src.data.pipeline import prepare_data, _read_csv_bytes, load_csv_url
from src.analytics.metrics import kpis, group_summary, simulate
from src.analytics.metrics import period_comparison
from src.analytics.anomalies import detect_anomalies
from src.reporting.reports import build_report, excel_export, pdf_export
from src.cli import run

@pytest.fixture
def raw():
    return pd.DataFrame({"Order Date":["2024-01-01","bad","2024-01-03"],"Order ID":["a","b","a"],"Sales":[100,0,50],"Profit":[20,-2,5],"Discount":[0,.2,.5],"Category":["A","B","A"]})

def test_mapping_and_safe_conversion(raw):
    df, q = prepare_data(raw)
    assert df.sales.tolist() == [100,0,50]
    assert pd.isna(df.order_date.iloc[1]) and q["invalid_order_dates"] == 1
    assert pd.isna(df.profit_margin.iloc[1])
    assert q["negative_profit"] == 1

def test_aggregates_and_kpis(raw):
    df,_=prepare_data(raw); m=kpis(df)
    assert m["sales"] == 150 and m["profit"] == 23 and m["orders"] == 2
    assert m["margin"] == pytest.approx(23/150)
    assert group_summary(df,["category"]).set_index("category").loc["A","profit"] == 25

def test_discount_and_scenario(raw):
    df,_=prepare_data(raw)
    assert str(df.discount_band.iloc[2]) == "30–50%"
    result=simulate(kpis(df),10,0,0)
    assert result["scenario_sales"] == 165
    assert result["scenario_profit"] == pytest.approx(25.3)

def test_missing_required_column():
    with pytest.raises(ValueError, match="Required columns"):
        prepare_data(pd.DataFrame({"Sales":[1]}))

def test_hosted_csv_encoding_and_https_requirement():
    raw = _read_csv_bytes("Order Date,Sales,Profit\n1/2/2024,10,2\n".encode("cp1252"))
    df,_ = prepare_data(raw)
    assert df.sales.sum() == 10
    with pytest.raises(ValueError, match="HTTPS"):
        load_csv_url("http://example.com/data.csv")

def test_quality_rejects_bad_required_values_but_keeps_negative_profit():
    raw=pd.DataFrame({"Order Date":["bad","2024-01-01","2024-01-02"],"Sales":[3,"oops",0],"Profit":[1,-4,0]})
    df,q=prepare_data(raw)
    assert q["source_rows"]==3 and q["valid_rows"]==1 and q["rejected_rows"]==2
    assert df.quality_negative_profit.iloc[1]
    assert q["numeric_conversion_failures"]["sales"]==1

def test_fingerprint_key_preserves_duplicate_multiplicity():
    raw=pd.DataFrame({"Order Date":["2024-01-01"]*2,"Sales":[10,10],"Profit":[2,2]})
    df,q=prepare_data(raw)
    assert df.record_key.nunique()==2 and q["duplicate_rows"]==1

def test_period_comparison_equal_windows_and_zero_baseline():
    df,_=prepare_data(pd.DataFrame({"Order Date":["2024-01-01","2024-01-02","2024-01-03"],"Sales":[10,20,30],"Profit":[1,2,3]}))
    result=period_comparison(df,"2024-01-03","2024-01-03")
    assert result["metrics"]["sales"]["current"]==30
    assert result["metrics"]["sales"]["previous"]==20
    assert result["metrics"]["sales"]["absolute_change"]==10
    assert result["metrics"]["sales"]["percentage_change"]==pytest.approx(.5)

def test_anomaly_monthly_threshold_and_missing_baseline():
    dates=["2024-01-01","2024-02-01","2024-03-01","2024-04-01"]
    df,_=prepare_data(pd.DataFrame({"Order Date":dates,"Sales":[100,100,100,20],"Profit":[10,10,10,2]}))
    alerts=detect_anomalies(df,drop_pct=30,min_baseline=3)
    assert any(a["metric"]=="sales" and a["percentage_deviation"]==-80 for a in alerts)
    assert detect_anomalies(df.iloc[:2],min_baseline=3)==[]

def test_report_generation_and_exports():
    df,q=prepare_data(pd.DataFrame({"Order Date":["2024-01-01"],"Sales":[10],"Profit":[-2],"Product Name":["P"],"Category":["C"],"Region":["R"]}))
    report=build_report(df,q)
    assert report["kpis"]["profit"]==-2
    assert excel_export(report)[:2]==b"PK"
    with ZipFile(BytesIO(excel_export(report))) as workbook:
        assert workbook.testzip() is None
        assert "xl/worksheets/sheet1.xml" in workbook.namelist()
    assert pdf_export(report).startswith(b"%PDF")
    assert b"startxref" in pdf_export(report)

def test_cli_writes_reports_and_run_summary(tmp_path):
    source=tmp_path/"data.csv"
    source.write_text("Order Date,Sales,Profit\n2024-01-01,10,2\n",encoding="utf-8")
    result=run(source,str(tmp_path/"out"))
    assert result["status"]=="success" and result["valid_rows"]==1
    assert (tmp_path/"out"/"last_run.json").exists()
    with pytest.raises(FileNotFoundError): run(tmp_path/"missing.csv",str(tmp_path/"out"))
    import json
    assert json.loads((tmp_path/"out"/"last_run.json").read_text())["status"]=="failed"
    assert (tmp_path/"out"/"retailiq_quarantine.csv").exists()

def test_empty_data_and_zero_sales_are_safe():
    empty,_=prepare_data(pd.DataFrame({"Order Date":[],"Sales":[],"Profit":[]}))
    assert kpis(empty)["orders"]==0 and pd.isna(kpis(empty)["margin"])
    zeros,_=prepare_data(pd.DataFrame({"Order Date":["2024-01-01"],"Sales":[0],"Profit":[-3]}))
    assert kpis(zeros)["profit"]==-3 and pd.isna(kpis(zeros)["margin"])

def test_postgres_configuration_failure_is_clear(monkeypatch):
    monkeypatch.delenv("DATABASE_URL",raising=False)
    from src.database.postgres import engine_from_env
    with pytest.raises(RuntimeError,match="CSV mode"):
        engine_from_env()
