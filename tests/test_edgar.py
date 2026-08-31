import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_analysis import edgar
from stock_analysis.edgar import resolve_duration_quarters


def _entry(start, end, val, fy, fp, form, filed):
    return {"start": start, "end": end, "val": val, "fy": fy, "fp": fp, "form": form, "filed": filed}


def _instant(end, val, form, filed):
    return {"end": end, "val": val, "form": form, "filed": filed}


def _companyfacts(tag_entries: dict) -> dict:
    """tag adi -> ham fact listesi eslemesinden minimal bir companyfacts
    JSON'u uretir (tum degerler USD birimi altinda)."""
    return {
        "facts": {
            "us-gaap": {
                tag: {"units": {"USD": entries}} for tag, entries in tag_entries.items()
            }
        }
    }


def test_discrete_quarters_used_directly():
    # Sirket her ceyregi ayri ayri (3 aylik) raporluyor: dogrudan kullanilmali.
    entries = [
        _entry("2023-01-01", "2023-03-31", 100, 2023, "Q1", "10-Q", "2023-05-01"),
        _entry("2023-04-01", "2023-06-30", 110, 2023, "Q2", "10-Q", "2023-08-01"),
        _entry("2023-07-01", "2023-09-30", 120, 2023, "Q3", "10-Q", "2023-11-01"),
        _entry("2023-01-01", "2023-12-31", 460, 2023, "FY", "10-K", "2024-02-01"),
    ]
    result = resolve_duration_quarters(entries)

    assert result[(2023, "Q1")]["value"] == 100
    assert result[(2023, "Q1")]["derived"] is False
    assert result[(2023, "Q2")]["value"] == 110
    assert result[(2023, "Q2")]["derived"] is False
    assert result[(2023, "Q3")]["value"] == 120
    assert result[(2023, "Q3")]["derived"] is False
    # Q4 = 460 - (100+110+120) = 130
    assert result[(2023, "Q4")]["value"] == 130
    assert result[(2023, "Q4")]["derived"] is True


def test_cumulative_only_company_derives_quarters():
    # Sirket sadece yil-basindan-itibaren kumulatif deger veriyor.
    entries = [
        _entry("2023-01-01", "2023-03-31", 100, 2023, "Q1", "10-Q", "2023-05-01"),
        _entry("2023-01-01", "2023-06-30", 210, 2023, "Q2", "10-Q", "2023-08-01"),
        _entry("2023-01-01", "2023-09-30", 330, 2023, "Q3", "10-Q", "2023-11-01"),
        _entry("2023-01-01", "2023-12-31", 460, 2023, "FY", "10-K", "2024-02-01"),
    ]
    result = resolve_duration_quarters(entries)

    assert result[(2023, "Q1")]["value"] == 100
    # Q2 = 210 - 100 = 110, turetilmis
    assert result[(2023, "Q2")]["value"] == 110
    assert result[(2023, "Q2")]["derived"] is True
    # Q3 = 330 - 210 = 120, turetilmis
    assert result[(2023, "Q3")]["value"] == 120
    assert result[(2023, "Q3")]["derived"] is True
    # Q4 = 460 - (100+110+120) = 130
    assert result[(2023, "Q4")]["value"] == 130
    assert result[(2023, "Q4")]["derived"] is True


def test_missing_quarter_blocks_q4_derivation():
    # Q2 hicbir formda gelmiyor -> Q3 turetilemez, Q4 de turetilemez.
    entries = [
        _entry("2023-01-01", "2023-03-31", 100, 2023, "Q1", "10-Q", "2023-05-01"),
        _entry("2023-01-01", "2023-09-30", 330, 2023, "Q3", "10-Q", "2023-11-01"),
        _entry("2023-01-01", "2023-12-31", 460, 2023, "FY", "10-K", "2024-02-01"),
    ]
    result = resolve_duration_quarters(entries)

    assert (2023, "Q1") in result
    assert (2023, "Q2") not in result
    assert (2023, "Q3") not in result
    assert (2023, "Q4") not in result


def test_restatement_prefers_latest_filed():
    # Ayni donem icin iki kayit var (duzeltme); en son filed olan kullanilmali.
    entries = [
        _entry("2023-01-01", "2023-03-31", 100, 2023, "Q1", "10-Q", "2023-05-01"),
        _entry("2023-01-01", "2023-03-31", 105, 2023, "Q1", "10-Q/A", "2023-06-01"),
    ]
    result = resolve_duration_quarters(entries)
    assert result[(2023, "Q1")]["value"] == 105


def test_q1_duration_guard_rejects_mislabeled_entry():
    # fp="Q1" ama sure 180 gun (aslinda bir 6 aylik kayit yanlis etiketlenmis
    # olabilir) - kabul edilmemeli, "veri yok" kalmali.
    entries = [
        _entry("2023-01-01", "2023-06-30", 999, 2023, "Q1", "10-Q", "2023-05-01"),
    ]
    result = resolve_duration_quarters(entries)
    assert (2023, "Q1") not in result


def test_duration_tags_merge_across_tag_switch():
    # Sirket 2022'de eski etiketi, 2023'te yeni etiketi kullanmis (orn.
    # ASC 606 sonrasi gelir etiketi degisimi). Tek etikette durulursa 2022
    # tamamen kaybolur; birlestirme ile her ikisi de gelmeli.
    old_tag_entries = [
        _entry("2022-01-01", "2022-03-31", 100, 2022, "Q1", "10-Q", "2022-05-01"),
        _entry("2022-04-01", "2022-06-30", 110, 2022, "Q2", "10-Q", "2022-08-01"),
        _entry("2022-07-01", "2022-09-30", 120, 2022, "Q3", "10-Q", "2022-11-01"),
        _entry("2022-01-01", "2022-12-31", 460, 2022, "FY", "10-K", "2023-02-01"),
    ]
    new_tag_entries = [
        _entry("2023-01-01", "2023-03-31", 200, 2023, "Q1", "10-Q", "2023-05-01"),
    ]
    companyfacts = _companyfacts({"NewRevenueTag": new_tag_entries, "OldRevenueTag": old_tag_entries})
    combined = edgar._load_priority_entries(companyfacts, ["NewRevenueTag", "OldRevenueTag"])
    result = resolve_duration_quarters(combined)

    assert result[(2022, "Q1")]["value"] == 100
    assert result[(2022, "Q1")]["tag"] == "OldRevenueTag"
    assert result[(2022, "Q4")]["value"] == 130
    assert result[(2023, "Q1")]["value"] == 200
    assert result[(2023, "Q1")]["tag"] == "NewRevenueTag"


def test_duration_tag_priority_wins_over_later_filed():
    # Ayni donem icin iki FARKLI etikette kayit var; oncelikli etiket
    # (config sirasinda once gelen), daha gec filed olsa bile kazanmamali -
    # etiket onceligi filed tarihinden once gelir.
    priority_entries = [
        _entry("2023-01-01", "2023-03-31", 100, 2023, "Q1", "10-Q", "2023-05-01"),
    ]
    fallback_entries = [
        _entry("2023-01-01", "2023-03-31", 999, 2023, "Q1", "10-Q", "2023-05-02"),
    ]
    companyfacts = _companyfacts({"PriorityTag": priority_entries, "FallbackTag": fallback_entries})
    combined = edgar._load_priority_entries(companyfacts, ["PriorityTag", "FallbackTag"])
    result = resolve_duration_quarters(combined)

    assert result[(2023, "Q1")]["value"] == 100
    assert result[(2023, "Q1")]["tag"] == "PriorityTag"


def test_instant_metric_does_not_mix_definitions_across_quarters():
    # LongTermDebtNoncurrent ve LongTermDebt farkli tanimlar; sirketin
    # herhangi bir ceyregi icin veri olan ILK etiket sirket genelinde sabit
    # kullanilmali, diger etigin verisi olan bir baska ceyrek icin bile
    # otomatik gecis yapilmamali.
    companyfacts = {
        "facts": {
            "us-gaap": {
                "LongTermDebtNoncurrent": {"units": {"USD": [
                    _instant("2022-12-31", 500, "10-K", "2023-02-01"),
                ]}},
                "LongTermDebt": {"units": {"USD": [
                    _instant("2023-03-31", 600, "10-Q", "2023-05-01"),
                ]}},
            }
        }
    }
    wanted = {"2022-12-31", "2023-03-31"}
    tag_used, resolved = edgar._resolve_instant_metric(
        companyfacts, ["LongTermDebtNoncurrent", "LongTermDebt"], wanted
    )

    assert tag_used == "LongTermDebtNoncurrent"
    assert "2022-12-31" in resolved
    assert "2023-03-31" not in resolved


def test_build_quarters_computes_eps_and_sums_commercial_paper():
    companyfacts = {
        "facts": {
            "us-gaap": {
                "Revenues": {"units": {"USD": [
                    _entry("2023-01-01", "2023-03-31", 1000, 2023, "Q1", "10-Q", "2023-05-01"),
                ]}},
                "NetIncomeLoss": {"units": {"USD": [
                    _entry("2023-01-01", "2023-03-31", 200, 2023, "Q1", "10-Q", "2023-05-01"),
                ]}},
                "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [
                    _entry("2023-01-01", "2023-03-31", 100, 2023, "Q1", "10-Q", "2023-05-01"),
                ]}},
                "ShortTermBorrowings": {"units": {"USD": [
                    _instant("2023-03-31", 50, "10-Q", "2023-05-01"),
                ]}},
                "CommercialPaper": {"units": {"USD": [
                    _instant("2023-03-31", 30, "10-Q", "2023-05-01"),
                ]}},
            }
        }
    }
    quarters = edgar.build_quarters(companyfacts)
    q = quarters["2023-Q1"]

    assert q["metrics"]["eps_diluted"]["value"] == 2.0
    assert q["metrics"]["eps_diluted"]["derived"] is True
    assert "gross_profit" not in q["metrics"]
    assert q["metrics"]["short_term_debt"]["value"] == 80
