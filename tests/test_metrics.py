import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_analysis.metrics import (
    classify_financing_arm,
    compute_quarter_derived,
    compute_ttm,
    compute_valuation_context,
    compute_valuation_history,
    compute_valuation_ratios,
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


def _ttm(revenue=1000, net_income=100, eps=1.0, fcf=200, ebitda=300):
    return {
        "available": True,
        "period_end": "2024-03-31",
        "revenue": revenue,
        "net_income": net_income,
        "eps_diluted": eps,
        "fcf": fcf,
        "ebitda": ebitda,
    }


def test_pe_unavailable_when_ttm_net_income_negative():
    # Zarar durumunda F/K hesaplanmaz (negatif bir sayi yanlislikla "ucuz"
    # gibi okunabiliyordu) - deger None kalir ve gerekce isaretlenir.
    ttm = _ttm(net_income=-500, eps=-5.0)
    valuation = compute_valuation_ratios(ttm, market_cap=1000, price=10.0, cash=50, total_debt=100)

    assert valuation["pe"] is None
    assert valuation["unavailable_reasons"]["pe"] == "hesaplanamaz (zarar)"
    # Diger oranlar zarar kuralindan etkilenmemeli.
    assert valuation["ps"] is not None


def test_p_fcf_unavailable_when_ttm_fcf_negative():
    ttm = _ttm(fcf=-100)
    valuation = compute_valuation_ratios(ttm, market_cap=1000, price=10.0, cash=50, total_debt=100)

    assert valuation["p_fcf"] is None
    assert valuation["unavailable_reasons"]["p_fcf"] == "hesaplanamaz (zarar)"


def test_pe_and_p_fcf_available_when_ttm_positive():
    ttm = _ttm()
    valuation = compute_valuation_ratios(ttm, market_cap=1000, price=10.0, cash=50, total_debt=100)

    assert valuation["pe"] == 10.0
    assert valuation["unavailable_reasons"]["pe"] is None
    assert valuation["p_fcf"] is not None
    assert valuation["unavailable_reasons"]["p_fcf"] is None


def _val_quarter_with_income(period_end, revenue, net_income, eps, shares, ocf, capex):
    metrics = dict(_BASE_METRICS)
    metrics["revenue"] = _m(revenue)
    metrics["net_income"] = _m(net_income)
    metrics["eps_diluted"] = _m(eps)
    metrics["diluted_shares"] = _m(shares)
    metrics["operating_cash_flow"] = _m(ocf)
    metrics["capex"] = _m(capex)
    metrics["operating_income"] = _m(None)
    metrics["depreciation_amortization"] = _m(None)
    return {"period_end": period_end, "metrics": metrics}


def test_valuation_history_excludes_loss_quarter_from_pe_series():
    # Son ceyrekte TTM net kar negatife donuyor (zarar) - o ceyrek icin P/E
    # None birakilmali ve seriye (dolayisiyla yuzdelik havuzuna) hic
    # girmemeli.
    quarters = {
        "2023-Q1": _val_quarter_with_income("2023-03-31", 100, 10, 1.0, 50, 20, 0),
        "2023-Q2": _val_quarter_with_income("2023-06-30", 100, 10, 1.0, 50, 20, 0),
        "2023-Q3": _val_quarter_with_income("2023-09-30", 100, 10, 1.0, 50, 20, 0),
        "2023-Q4": _val_quarter_with_income("2023-12-31", 100, -500, -10.0, 50, 20, 0),
    }
    price_history = [{"date": f"2023-{i * 3:02d}-28", "close": 20.0} for i in range(1, 5)]

    history = compute_valuation_history(quarters, price_history)

    assert history["pe"] == []


def test_classify_financing_arm_detects_keyword_in_summary():
    result = classify_financing_arm(
        "Company operates an automotive segment and a Financial Services segment "
        "that provides wholesale and retail financing to dealers and customers."
    )
    assert result["has_financing_arm"] is True
    assert result["reason"]
    assert result["signal"] == "business_summary"
    assert result["matched"] == "financial services segment"


def test_classify_financing_arm_false_when_no_keyword():
    result = classify_financing_arm("A software company that builds cloud tools.")
    assert result == {"has_financing_arm": False, "reason": None, "signal": None, "matched": None}


def test_classify_financing_arm_handles_none_summary():
    assert classify_financing_arm(None) == {
        "has_financing_arm": False,
        "reason": None,
        "signal": None,
        "matched": None,
    }


def test_classify_financing_arm_second_signal_from_xbrl_tag_when_text_silent():
    # Kunye metni finansman kolundan hic bahsetmiyor (yfinance ozeti
    # degisebilir/eksik olabilir) ama companyfacts'te FinanceReceivables
    # etiketi var - yapisal sinyal metin sinyali olmadan da yeterli olmali.
    companyfacts = {
        "facts": {
            "us-gaap": {
                "FinanceReceivablesNetNoncurrent": {
                    "units": {"USD": [{"end": "2023-03-31", "val": 1000, "form": "10-Q", "filed": "2023-05-01"}]}
                }
            }
        }
    }
    result = classify_financing_arm("A generic industrial manufacturer.", companyfacts)

    assert result["has_financing_arm"] is True
    assert result["signal"] == "xbrl_tag"
    assert result["matched"] == "FinanceReceivablesNetNoncurrent"


def test_classify_financing_arm_text_signal_wins_over_xbrl_when_both_present():
    companyfacts = {
        "facts": {
            "us-gaap": {
                "NotesReceivableNet": {
                    "units": {"USD": [{"end": "2023-03-31", "val": 1000, "form": "10-Q", "filed": "2023-05-01"}]}
                }
            }
        }
    }
    result = classify_financing_arm(
        "The company operates a financing segment for dealers.", companyfacts
    )

    assert result["signal"] == "business_summary"


def test_classify_financing_arm_false_when_neither_signal_present():
    companyfacts = {"facts": {"us-gaap": {}}}
    result = classify_financing_arm("A generic industrial manufacturer.", companyfacts)

    assert result["has_financing_arm"] is False
