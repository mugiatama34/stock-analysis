import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_analysis import metrics, render

_RAW_KEYS = (
    "revenue", "cost_of_revenue", "operating_income", "net_income",
    "operating_cash_flow", "capex", "depreciation_amortization",
    "interest_expense", "cash_and_equivalents", "total_debt",
    "short_term_debt", "long_term_debt", "diluted_shares", "eps_diluted",
)


def _m(value):
    return {"value": value, "tag": None, "derived": False}


def _quarter(fiscal_year, fiscal_quarter, period_end, **raw_overrides):
    quarter_metrics = {key: _m(raw_overrides.get(key)) for key in _RAW_KEYS}
    derived = metrics.compute_quarter_derived(quarter_metrics)
    return {
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "period_end": period_end,
        "form": "10-Q",
        "filed": period_end,
        "metrics": quarter_metrics,
        "derived_metrics": derived,
    }


def _base_data(**overrides):
    quarters = {
        "2023-Q1": _quarter(2023, 1, "2023-03-31"),
        "2023-Q2": _quarter(2023, 2, "2023-06-30"),
        "2023-Q3": _quarter(2023, 3, "2023-09-30"),
        "2023-Q4": _quarter(2023, 4, "2023-12-31"),
        "2024-Q1": _quarter(
            2024, 1, "2024-03-31",
            revenue=1000, cost_of_revenue=600, net_income=100, operating_cash_flow=150,
            capex=20, total_debt=500, cash_and_equivalents=200,
        ),
    }
    data = {
        "ticker": "TEST",
        "company_name": "Test Corp",
        "sector": "Technology",
        "industry": "Software",
        "employees": 1000,
        "market_cap": 5_000_000_000,
        "business_summary": "Test Corp bir yazilim sirketidir.",
        "sector_flag": {"is_financial_sector": False, "reason": None},
        "quarters": quarters,
        "valuation": {"available": False, "reason": "TTM verisi yok"},
        "valuation_context": {},
        "peers": {"status": "ok", "peers": []},
    }
    data.update(overrides)
    return data


def test_sector_rule_hides_margins_with_reason_not_blank():
    data = _base_data(
        sector_flag={
            "is_financial_sector": True,
            "reason": "Sektor/endustri bilgisinde 'bank' tespit edildi; borc ve nakit temelli oranlar bu sektorde anlamsiz.",
        }
    )

    output = render.render_report(data, generated_at="2026-08-31")

    assert "borc ve nakit temelli oranlar bu sektorde anlamsiz" in output
    # gizlenen brut marj (0.4) sayisal olarak gorunmemeli
    assert "%40.0" not in output


def test_coverage_rule_hides_metric_present_in_only_one_of_five_quarters():
    # Sadece son ceyrekte revenue var (1/5 = %20 < %30 esigi) - deger o
    # ceyrekte GERCEKTEN mevcut olsa bile genel kapsam yetersizligi
    # yuzunden gizlenmeli.
    quarters = {
        "2023-Q1": _quarter(2023, 1, "2023-03-31"),
        "2023-Q2": _quarter(2023, 2, "2023-06-30"),
        "2023-Q3": _quarter(2023, 3, "2023-09-30"),
        "2023-Q4": _quarter(2023, 4, "2023-12-31"),
        "2024-Q1": _quarter(2024, 1, "2024-03-31", revenue=123456),
    }
    data = _base_data(quarters=quarters)

    output = render.render_report(data, generated_at="2026-08-31")

    assert "%20" in output
    assert "eşiğinin altında" in output
    assert "$123.46K" not in output


def test_peers_unavailable_shows_single_reason_no_table():
    data = _base_data(peers={"status": "unavailable", "peers": [], "reason": "baglanti hatasi"})

    output = render.render_report(data, generated_at="2026-08-31")

    assert "Rakip verisi alınamadı" in output
    assert "baglanti hatasi" in output
    assert "<table" not in output


def test_peer_margin_uses_finnhub_percent_scale_directly():
    # Finnhub grossMarginTTM zaten yuzde olceginde gelir (45.2 = %45.2);
    # kendi hesapladigimiz fraksiyon (0-1) gibi 100 ile CARPILMAMALI.
    data = _base_data(
        peers={
            "status": "ok",
            "peers": [{"ticker": "PEER1", "status": "ok", "pe_ttm": 18.5, "gross_margin_ttm": 45.2}],
        }
    )

    output = render.render_report(data, generated_at="2026-08-31")

    assert "%45.2" in output
    assert "%4520.0" not in output


def test_peer_with_unavailable_snapshot_shows_reason_per_cell():
    data = _base_data(
        peers={
            "status": "ok",
            "peers": [{"ticker": "PEER1", "status": "unavailable", "reason": "hata"}],
        }
    )

    output = render.render_report(data, generated_at="2026-08-31")

    assert "PEER1" in output
    assert "veri alınamadı" in output


def test_header_shows_two_distinct_dates():
    data = _base_data()

    output = render.render_report(data, generated_at="2026-08-31")

    assert "Veri son çeyrek: 2024-03-31" in output
    assert "Rapor üretim tarihi: 2026-08-31" in output


def test_valuation_unavailable_shows_reason_not_crash():
    data = _base_data(valuation={"available": False, "reason": "son 4 ceyrek tamamlanmadi"})

    output = render.render_report(data, generated_at="2026-08-31")

    assert "son 4 ceyrek tamamlanmadi" in output


def test_valuation_percentile_shown_when_history_sufficient():
    data = _base_data(
        valuation={"available": True, "pe": 20.0, "ps": None, "ev_ebitda": None, "p_fcf": None},
        valuation_context={"pe": {"status": "ok", "quarters_used": 20, "percentile": 63.2}},
    )

    output = render.render_report(data, generated_at="2026-08-31")

    assert "63. yüzdelik" in output
    assert "20 çeyrek" in output


def test_valuation_insufficient_history_shows_raw_ratio_and_count():
    data = _base_data(
        valuation={"available": True, "pe": 20.0, "ps": None, "ev_ebitda": None, "p_fcf": None},
        valuation_context={"pe": {"status": "insufficient_history", "quarters_used": 14}},
    )

    output = render.render_report(data, generated_at="2026-08-31")

    assert "20.00" in output
    assert "14 çeyrek mevcut" in output


def test_sector_and_industry_translated_to_turkish():
    data = _base_data(sector="Technology", industry="Software - Application")

    output = render.render_report(data, generated_at="2026-08-31")

    assert "Teknoloji" in output
    assert "Yazılım - Uygulama" in output
    assert "Technology" not in output
    assert "Software - Application" not in output


def test_unknown_sector_and_industry_fall_back_to_english():
    data = _base_data(sector="Some New Sector", industry="Some New Industry")

    output = render.render_report(data, generated_at="2026-08-31")

    assert "Some New Sector" in output
    assert "Some New Industry" in output


def test_short_business_summary_has_no_expand_link():
    data = _base_data(business_summary="Kısa bir açıklama.")

    output = render.render_report(data, generated_at="2026-08-31")

    assert "Kısa bir açıklama." in output
    assert "Devamını göster" not in output


def test_long_business_summary_is_truncated_at_sentence_boundary_with_expand_link():
    first_sentence = "A" * 350 + "."
    second_sentence = " " + "B" * 200 + "."
    data = _base_data(business_summary=first_sentence + second_sentence)

    output = render.render_report(data, generated_at="2026-08-31")

    assert first_sentence in output
    assert "Devamını göster" in output
    assert "B" * 200 in output
    # kirpilan kisa metin, tam metnin bir alt dizesi olarak degil, ayri
    # bir yerde (details icinde) gorunmeli - kirpma noktasi cumle sonuydu
    assert output.index(first_sentence) < output.index("Devamını göster")


def test_business_summary_without_sentence_boundary_hard_truncates_with_ellipsis():
    data = _base_data(business_summary="A" * 500)

    output = render.render_report(data, generated_at="2026-08-31")

    assert ("A" * 400 + "…") in output
    assert "Devamını göster" in output
