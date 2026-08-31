import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_analysis.metrics import (
    compute_quarter_derived,
    compute_ttm,
    compute_valuation_context,
    compute_valuation_history,
    latest_quarter,
)


def _m(value):
    return {"value": value, "tag": None, "derived": False}


_BASE_METRICS = {
    "revenue": _m(None),
    "cost_of_revenue": _m(None),
    "operating_income": _m(None),
    "net_income": _m(None),
    "operating_cash_flow": _m(None),
    "capex": _m(None),
    "depreciation_amortization": _m(None),
    "interest_expense": _m(None),
    "cash_and_equivalents": _m(None),
    "short_term_debt": _m(None),
    "long_term_debt": _m(None),
    "total_debt": _m(None),
}


def test_gross_profit_always_computed_not_read_from_tag():
    # quarter_metrics'te "gross_profit" anahtari HIC yok (artik XBRL'den
    # cekilmiyor) - yine de gross_margin gelir - satis maliyetinden
    # hesaplanmali. Anahtar olsaydi bile KeyError vermezdi eskiden ama artik
    # kod bu anahtari hic okumuyor; bu test onu dogrular.
    quarter_metrics = dict(_BASE_METRICS)
    quarter_metrics["revenue"] = _m(1000)
    quarter_metrics["cost_of_revenue"] = _m(600)

    derived = compute_quarter_derived(quarter_metrics)

    assert derived["gross_margin"] == 0.4


def test_net_debt_reads_total_debt_directly_not_recomputed_from_components():
    # total_debt artik EDGAR katmaninda (edgar._resolve_instant_chain_with_fallback)
    # cozulen dogrudan bir metriktir; compute_quarter_derived onu
    # short_term_debt/long_term_debt'ten YENIDEN toplamamali, quarter_metrics
    # icindeki hazir degeri okumali. short_term_debt/long_term_debt burada
    # BILEREK total_debt'ten FARKLI degerlere sahip - eger kod hala eski
    # sekilde bunlari toplasaydi net_debt yanlis cikardi.
    quarter_metrics = dict(_BASE_METRICS)
    quarter_metrics["short_term_debt"] = _m(999)
    quarter_metrics["long_term_debt"] = _m(999)
    quarter_metrics["total_debt"] = _m(500)
    quarter_metrics["cash_and_equivalents"] = _m(200)

    derived = compute_quarter_derived(quarter_metrics)

    assert derived["total_debt"] == 500
    assert derived["net_debt"] == 300


def test_gross_profit_missing_when_inputs_missing():
    quarter_metrics = dict(_BASE_METRICS)
    quarter_metrics["revenue"] = _m(1000)
    # cost_of_revenue eksik -> tahmin etmeden "veri yok" kalmali.

    derived = compute_quarter_derived(quarter_metrics)

    assert derived["gross_margin"] is None


def _quarter(period_end, revenue, net_income, eps, ocf):
    metrics = dict(_BASE_METRICS)
    metrics["revenue"] = _m(revenue)
    metrics["net_income"] = _m(net_income)
    metrics["eps_diluted"] = _m(eps)
    metrics["operating_cash_flow"] = _m(ocf)
    metrics["capex"] = _m(0)
    return {"period_end": period_end, "metrics": metrics}


def test_ttm_period_end_always_matches_latest_resolved_quarter():
    # ttm.period_end, en son COZULEBILEN ceyregin donem sonu olmali - ayri
    # bir "TTM penceresi" hesaplanmiyor, ayni son-4-ceyrek secimine dayaniyor.
    quarters = {
        f"2023-Q{i}": _quarter(f"2023-{i * 3:02d}-28", 100, 10, 1.0, 20)
        for i in range(1, 5)
    }
    ttm = compute_ttm(quarters)
    latest = latest_quarter(quarters)

    assert ttm["available"] is True
    assert ttm["period_end"] == latest["period_end"]


def _val_quarter(period_end, revenue, eps, shares):
    metrics = dict(_BASE_METRICS)
    metrics["revenue"] = _m(revenue)
    metrics["eps_diluted"] = _m(eps)
    metrics["diluted_shares"] = _m(shares)
    metrics["operating_cash_flow"] = _m(None)
    metrics["capex"] = _m(None)
    metrics["operating_income"] = _m(None)
    metrics["depreciation_amortization"] = _m(None)
    return {"period_end": period_end, "metrics": metrics}


def test_valuation_history_needs_four_quarters_before_producing_a_ratio():
    # Ilk 3 ceyrekte trailing-TTM penceresi tamamlanmadigi icin hicbir oran
    # uretilmemeli; 4. ceyrekte (indeks 3) ilk P/E ortaya cikmali.
    quarters = {
        f"2023-Q{i}": _val_quarter(f"2023-{i * 3:02d}-28", 100, 1.0, 50)
        for i in range(1, 5)
    }
    price_history = [{"date": f"2023-{i * 3:02d}-28", "close": 20.0} for i in range(1, 5)]

    history = compute_valuation_history(quarters, price_history)

    assert len(history["pe"]) == 1
    # TTM EPS = 1.0 * 4 = 4.0; fiyat 20.0 -> P/E = 5.0
    assert history["pe"][0] == 5.0
    # TTM revenue = 100*4=400; market_cap = price*shares = 20*50=1000 -> P/S=2.5
    assert history["ps"][0] == 2.5


def test_valuation_history_skips_quarter_without_matching_price():
    # price_history'de bir ceyrek sonundan ONCE hic islem gunu yoksa o
    # ceyrek tahmini bir fiyatla doldurulmamali, tamamen atlanmali.
    quarters = {
        f"2023-Q{i}": _val_quarter(f"2023-{i * 3:02d}-28", 100, 1.0, 50)
        for i in range(1, 5)
    }
    price_history = [{"date": "2023-12-29", "close": 20.0}]  # tum ceyrek sonlarindan sonra

    history = compute_valuation_history(quarters, price_history)

    assert history["pe"] == []
    assert history["ps"] == []


def test_valuation_context_status_thresholds():
    # 12'nin altinda -> yuzdelik yok (insufficient_history). 12-19 arasi ->
    # yuzdelik hesaplanir ama kac ceyrege dayandigi bildirilir. Veri hic
    # yoksa (bos seri) -> no_data.
    valuation = {"available": True, "pe": 10.0, "ps": None, "ev_ebitda": 5.0, "p_fcf": 5.0}
    history = {
        "pe": [5.0] * 11,
        "ps": [],
        "ev_ebitda": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 6.0, 6.0, 6.0, 6.0, 6.0, 6.0],
        "p_fcf": [],
    }

    context = compute_valuation_context(history, valuation)

    assert context["pe"]["status"] == "insufficient_history"
    assert context["pe"]["quarters_used"] == 11
    assert context["ps"]["status"] == "no_data"
    assert context["ev_ebitda"]["status"] == "ok"
    assert context["ev_ebitda"]["quarters_used"] == 12
    # ev_ebitda=5.0 gecmis serisinde <=5.0 olan 5 nokta var (1,2,3,4,5) / 12
    assert round(context["ev_ebitda"]["percentile"], 2) == round(5 / 12 * 100, 2)
    assert context["p_fcf"]["status"] == "no_data"


def test_valuation_context_unavailable_when_valuation_not_available():
    context = compute_valuation_context({"pe": [1.0] * 20}, {"available": False, "reason": "x"})
    assert context == {}
