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
    return {"period_end": period_end, "metrics": entry_metrics}


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
