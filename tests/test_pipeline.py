import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_analysis import config, errors, pipeline


def _entry(start, end, val, fy, fp, form, filed):
    return {"start": start, "end": end, "val": val, "fy": fy, "fp": fp, "form": form, "filed": filed}


def test_insufficient_quarterly_data_raises_before_building_report(monkeypatch):
    # ASML deseni: CIK bulunuyor ama sirket 20-F/6-K dosyaladigi icin
    # companyfacts'te 10-Q/10-K kaynakli veri config.MIN_USABLE_QUARTERS'in
    # (8) altinda kaliyor - burada sadece 2 ceyrek var. Pipeline bu noktada
    # durmali; yfinance/Finnhub gibi rapor icin gereken sonraki adimlara HIC
    # gecmemeli (asagidaki sahteler cagrilirsa test patlar).
    companyfacts = {
        "facts": {
            "us-gaap": {
                "Revenues": {"units": {"USD": [
                    _entry("2023-01-01", "2023-03-31", 1000, 2023, "Q1", "10-Q", "2023-05-01"),
                    _entry("2023-04-01", "2023-06-30", 1100, 2023, "Q2", "10-Q", "2023-08-01"),
                ]}},
            }
        }
    }

    monkeypatch.setattr(pipeline.edgar, "get_cik", lambda ticker: "0000000001")
    monkeypatch.setattr(pipeline.yfinance_source, "fetch_splits", lambda ticker: [])
    monkeypatch.setattr(pipeline.cache, "load_cache", lambda ticker: {"quarters": {}})
    monkeypatch.setattr(pipeline.edgar, "fetch_companyfacts", lambda cik: companyfacts)

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError(
            "asgari ceyrek kontrolu bu adimdan ONCE durmali - rapor insasina hic gecilmemeli"
        )

    monkeypatch.setattr(pipeline.cache, "save_cache", _must_not_be_called)
    monkeypatch.setattr(pipeline.yfinance_source, "fetch_company_info", _must_not_be_called)
    monkeypatch.setattr(pipeline.yfinance_source, "fetch_price_history", _must_not_be_called)
    monkeypatch.setattr(pipeline.finnhub_source, "fetch_peers", _must_not_be_called)

    try:
        pipeline.fetch_stock_data("ASML")
    except errors.InsufficientQuarterlyDataError as exc:
        assert "2" in str(exc)
        assert str(config.MIN_USABLE_QUARTERS) in str(exc)
    else:
        raise AssertionError("errors.InsufficientQuarterlyDataError bekleniyordu")


def test_sufficient_quarterly_data_does_not_raise(monkeypatch):
    # Tam config.MIN_USABLE_QUARTERS (8 = 2 tam mali yil) kadar ceyrek
    # varsa esik asilmamis sayilmali (>= karsilastirmasi) - kontrol
    # yanlislikla sinirdaki sirketleri de reddetmemeli. Her mali yil icin
    # ayrik Q1-Q3 + yillik (10-K) kayit veriliyor (Q4 bundan turetilir) -
    # resolve_duration_quarters yillik/kumulatif bir capa olmadan cok
    # yila yayilan ayrik zinciri guvenilir sekilde capalayamiyor (bkz.
    # edgar.resolve_duration_quarters docstring'i).
    entries = []
    for year in (2020, 2021):
        entries += [
            _entry(f"{year}-01-01", f"{year}-03-31", 100, year, "Q1", "10-Q", f"{year}-05-01"),
            _entry(f"{year}-04-01", f"{year}-06-30", 110, year, "Q2", "10-Q", f"{year}-08-01"),
            _entry(f"{year}-07-01", f"{year}-09-30", 120, year, "Q3", "10-Q", f"{year}-11-01"),
            _entry(f"{year}-01-01", f"{year}-12-31", 460, year, "FY", "10-K", f"{year + 1}-02-01"),
        ]
    companyfacts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": entries}}}}}

    monkeypatch.setattr(pipeline.edgar, "get_cik", lambda ticker: "0000000001")
    monkeypatch.setattr(pipeline.yfinance_source, "fetch_splits", lambda ticker: [])
    monkeypatch.setattr(pipeline.cache, "load_cache", lambda ticker: {"quarters": {}})
    monkeypatch.setattr(pipeline.edgar, "fetch_companyfacts", lambda cik: companyfacts)
    monkeypatch.setattr(pipeline.cache, "save_cache", lambda ticker, cik, quarters: None)
    monkeypatch.setattr(
        pipeline.yfinance_source,
        "fetch_company_info",
        lambda ticker: {k: None for k in (
            "company_name", "sector", "industry", "employees",
            "market_cap", "current_price", "shares_outstanding",
        )},
    )
    monkeypatch.setattr(pipeline.yfinance_source, "fetch_price_history", lambda ticker: [])
    monkeypatch.setattr(
        pipeline.finnhub_source, "fetch_peers", lambda ticker: {"status": "ok", "peers": []}
    )

    data = pipeline.fetch_stock_data("XYZ")
    assert len(data["quarters"]) >= config.MIN_USABLE_QUARTERS
