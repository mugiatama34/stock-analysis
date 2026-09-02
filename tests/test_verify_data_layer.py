import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from stock_analysis import config
import verify_data_layer


def _instant_entry(value, tag):
    return {"value": value, "tag": tag, "derived": False}


def _quarter(period_end, **metrics):
    entry_metrics = {
        metric: _instant_entry(None, None) for metric in config.INSTANT_METRICS
    }
    entry_metrics.update(metrics)
    return {
        "period_end": period_end,
        "fiscal_year": int(period_end[:4]),
        "metrics": entry_metrics,
    }


def test_continuity_warning_raised_on_tag_switch_with_big_jump():
    # JPM/F deseni: long_term_debt bir ceyrekte LongTermDebtNoncurrent
    # (800), sonraki ceyrekte LongTermDebt'e (1500) geciyor - etiket
    # degisimiyle birlikte %35 esigin cok ustunde bir sicrama var. Bu
    # kontrol olmasaydi tanim karisikligi sessizce gecerdi.
    ordered = [
        ("2023-Q1", _quarter("2023-03-31", long_term_debt=_instant_entry(800, "LongTermDebtNoncurrent"))),
        ("2023-Q2", _quarter("2023-06-30", long_term_debt=_instant_entry(1500, "LongTermDebt"))),
    ]
    warnings = verify_data_layer._continuity_warnings(
        ordered, "long_term_debt", config.INSTANT_METRIC_CONTINUITY_THRESHOLD
    )

    assert len(warnings) == 1
    w = warnings[0]
    assert w["quarter"] == "2023-Q2"
    assert w["prev_quarter"] == "2023-Q1"
    assert w["prev_tag"] == "LongTermDebtNoncurrent"
    assert w["new_tag"] == "LongTermDebt"
    assert w["relative_jump"] > config.INSTANT_METRIC_CONTINUITY_THRESHOLD


def test_no_continuity_warning_when_tag_unchanged_despite_big_jump():
    # Etiket AYNI kalirken buyuk bir sicrama (orn. gercek bir borclanma
    # turu) veri kalitesi sorunu degildir - bu kontrol SADECE etiket
    # degisimiyle CAKISAN sicramalari isaretler.
    ordered = [
        ("2023-Q1", _quarter("2023-03-31", long_term_debt=_instant_entry(800, "LongTermDebt"))),
        ("2023-Q2", _quarter("2023-06-30", long_term_debt=_instant_entry(2000, "LongTermDebt"))),
    ]
    warnings = verify_data_layer._continuity_warnings(
        ordered, "long_term_debt", config.INSTANT_METRIC_CONTINUITY_THRESHOLD
    )
    assert warnings == []


def test_no_continuity_warning_when_jump_under_threshold():
    ordered = [
        ("2023-Q1", _quarter("2023-03-31", long_term_debt=_instant_entry(1000, "LongTermDebtNoncurrent"))),
        ("2023-Q2", _quarter("2023-06-30", long_term_debt=_instant_entry(1100, "LongTermDebt"))),
    ]
    warnings = verify_data_layer._continuity_warnings(
        ordered, "long_term_debt", config.INSTANT_METRIC_CONTINUITY_THRESHOLD
    )
    assert warnings == []


def test_continuity_check_compares_against_last_filled_quarter_across_gap():
    # Aradaki ceyrek "veri yok" (bosluk) - kiyaslama bir onceki GERCEKTEN
    # DOLU ceyrege gore yapilmali, bosluk atlanmali.
    ordered = [
        ("2023-Q1", _quarter("2023-03-31", long_term_debt=_instant_entry(800, "LongTermDebtNoncurrent"))),
        ("2023-Q2", _quarter("2023-06-30")),  # veri yok
        ("2023-Q3", _quarter("2023-09-30", long_term_debt=_instant_entry(1500, "LongTermDebt"))),
    ]
    warnings = verify_data_layer._continuity_warnings(
        ordered, "long_term_debt", config.INSTANT_METRIC_CONTINUITY_THRESHOLD
    )

    assert len(warnings) == 1
    assert warnings[0]["prev_quarter"] == "2023-Q1"
    assert warnings[0]["quarter"] == "2023-Q3"


def test_summarize_surfaces_continuity_warnings_at_top_level():
    data = {
        "quarters": {
            "2023-Q1": _quarter("2023-03-31", long_term_debt=_instant_entry(800, "LongTermDebtNoncurrent")),
            "2023-Q2": _quarter("2023-06-30", long_term_debt=_instant_entry(1500, "LongTermDebt")),
        }
    }
    summary = verify_data_layer.summarize(data)

    assert len(summary["continuity_warnings"]) == 1
    assert summary["continuity_warnings"][0]["metric"] == "long_term_debt"

    per_metric_warnings = summary["metrics"]["long_term_debt"]["continuity_warnings"]
    assert len(per_metric_warnings) == 1
    warning_without_metric = dict(summary["continuity_warnings"][0])
    del warning_without_metric["metric"]
    assert warning_without_metric == per_metric_warnings[0]


def test_summarize_flags_stopped_reporting_for_total_debt():
    # Ford deseni: total_debt son kez eski bir ceyrekte dolu, esikten fazla
    # ceyrek bosluk var - summarize bunu "reporting_status" altinda
    # raporlamali (verify_data_layer.py hem tablo hem net_debt satirinda
    # bunu okur).
    quarters = {
        "2019-Q1": _quarter("2019-03-31", total_debt=_instant_entry(400, "DebtAndCapitalLeaseObligations")),
        "2019-Q2": _quarter("2019-06-30", total_debt=_instant_entry(410, "DebtAndCapitalLeaseObligations")),
        "2020-Q2": _quarter("2020-06-30"),
        "2020-Q3": _quarter("2020-09-30"),
        "2020-Q4": _quarter("2020-12-31"),
        "2021-Q1": _quarter("2021-03-31"),
    }
    data = {"quarters": quarters}
    summary = verify_data_layer.summarize(data)

    status = summary["metrics"]["total_debt"]["reporting_status"]
    assert status["status"] == "stopped"
    assert status["last_filled_quarter"] == "2019-06-30"
    assert status["last_filled_year"] == 2019
    assert status["gap_quarters"] == 4


def test_summarize_net_debt_coverage_includes_reporting_status():
    quarters = {
        qkey: q
        for qkey, q in {
            "2019-Q1": _quarter("2019-03-31"),
            "2019-Q2": _quarter("2019-06-30"),
            "2020-Q2": _quarter("2020-06-30"),
            "2020-Q3": _quarter("2020-09-30"),
            "2020-Q4": _quarter("2020-12-31"),
            "2021-Q1": _quarter("2021-03-31"),
        }.items()
    }
    for qkey in ("2019-Q1", "2019-Q2"):
        quarters[qkey]["derived_metrics"] = {"net_debt": 300}

    data = {"quarters": quarters}
    summary = verify_data_layer.summarize(data)

    status = summary["net_debt_coverage"]["reporting_status"]
    assert status["status"] == "stopped"
    assert status["last_filled_quarter"] == "2019-06-30"
