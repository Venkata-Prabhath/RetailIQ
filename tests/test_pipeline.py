import pandas as pd
import pytest
from src.data.pipeline import prepare_data, _read_csv_bytes, load_csv_url
from src.analytics.metrics import kpis, group_summary, simulate

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
