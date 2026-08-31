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


def test_comparative_fact_mislabeled_with_filing_fy_fp_does_not_corrupt_period():
    # Gercek AAPL verisinde gozlemlenen desen: bir filing'in icindeki
    # KARSILASTIRMALI (bir onceki yilin ayni ceyregi) fact, kendi donemi
    # yerine ICINDE GECTIGI filing'in guncel fy/fp'sini tasiyor. Iki farkli
    # gercek donem (2008-Q1 ve 2009-Q1) SEC verisinde ayni fy/fp=(2010,Q1)
    # etiketini paylasiyor - gruplama fy/fp'ye degil tarihe dayanmali.
    entries = [
        # 2008-Q1'in kendi ozgun (dogru etiketli) filing'i.
        _entry("2008-09-28", "2008-12-27", 11880, 2009, "Q1", "10-Q", "2009-01-25"),
        # AYNI donem, FY2010-Q1 10-Q'sundaki YoY karsilastirma olarak tekrar
        # gorunuyor - SEC bunu YANLIS sekilde fy=2010,fp=Q1 etiketlemis.
        _entry("2008-09-28", "2008-12-27", 11880, 2010, "Q1", "10-Q", "2010-01-25"),
        # Gercek 2009-Q1 (=FY2010 Q1), ayni filing'in GUNCEL ceyregi.
        _entry("2009-09-27", "2009-12-26", 15683, 2010, "Q1", "10-Q", "2010-01-25"),
    ]
    result = resolve_duration_quarters(entries)

    assert result[(2009, "Q1")]["value"] == 11880
    assert result[(2010, "Q1")]["value"] == 15683


def test_average_metric_skips_q4_derivation_but_keeps_annual_marker():
    # diluted_shares agirlikli ortalamadir: yillik rakamdan Q1+Q2+Q3
    # cikarilarak Q4 turetilemez (103, 100+105+110=315'in "kalani" degil,
    # BAGIMSIZ bir yillik ortalamadir). allow_q4_derivation=False ile Q4
    # sonuc sozlugune hic girmemeli; yillik kayit ise EPS turetmesi icin
    # (fy, "_annual") altinda ayrica saklanmali.
    entries = [
        _entry("2023-01-01", "2023-03-31", 100, 2023, "Q1", "10-Q", "2023-05-01"),
        _entry("2023-04-01", "2023-06-30", 105, 2023, "Q2", "10-Q", "2023-08-01"),
        _entry("2023-07-01", "2023-09-30", 110, 2023, "Q3", "10-Q", "2023-11-01"),
        _entry("2023-01-01", "2023-12-31", 103, 2023, "FY", "10-K", "2024-02-01"),
    ]
    result = resolve_duration_quarters(entries, allow_q4_derivation=False)

    assert result[(2023, "Q1")]["value"] == 100
    assert (2023, "Q4") not in result
    assert result[(2023, "_annual")]["value"] == 103
    assert result[(2023, "_annual")]["derived"] is False


def test_build_quarters_leaves_q4_diluted_shares_empty_and_derives_eps_from_annual():
    # net_income (akis) Q4'u eskisi gibi cikararak turetir, ama
    # diluted_shares (ortalama) Q4'u BOS birakmali; eps_diluted Q4 ise
    # yillik EPS - (Q1+Q2+Q3 EPS) olarak hesaplanmali.
    companyfacts = {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {"units": {"USD": [
                    _entry("2023-01-01", "2023-03-31", 200, 2023, "Q1", "10-Q", "2023-05-01"),
                    _entry("2023-04-01", "2023-06-30", 200, 2023, "Q2", "10-Q", "2023-08-01"),
                    _entry("2023-07-01", "2023-09-30", 200, 2023, "Q3", "10-Q", "2023-11-01"),
                    _entry("2023-01-01", "2023-12-31", 1000, 2023, "FY", "10-K", "2024-02-01"),
                ]}},
                "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [
                    _entry("2023-01-01", "2023-03-31", 100, 2023, "Q1", "10-Q", "2023-05-01"),
                    _entry("2023-04-01", "2023-06-30", 100, 2023, "Q2", "10-Q", "2023-08-01"),
                    _entry("2023-07-01", "2023-09-30", 100, 2023, "Q3", "10-Q", "2023-11-01"),
                    _entry("2023-01-01", "2023-12-31", 100, 2023, "FY", "10-K", "2024-02-01"),
                ]}},
            }
        }
    }
    quarters = edgar.build_quarters(companyfacts)

    q1 = quarters["2023-Q1"]
    assert q1["metrics"]["eps_diluted"]["value"] == 2.0

    q4 = quarters["2023-Q4"]
    assert q4["metrics"]["net_income"]["value"] == 400
    assert q4["metrics"]["diluted_shares"]["value"] is None
    assert q4["metrics"]["eps_diluted"]["value"] == 4.0


def test_build_quarters_drops_quarters_before_min_fiscal_year():
    # 2009-Q1 tek basina duruyordu (2009'un diger uc ceyregi companyfacts'te
    # yok); seri 2010 mali yilindan itibaren baslamali (bkz. config.MIN_FISCAL_YEAR).
    companyfacts = {
        "facts": {
            "us-gaap": {
                "Revenues": {"units": {"USD": [
                    _entry("2009-01-01", "2009-03-31", 100, 2009, "Q1", "10-Q", "2009-05-01"),
                    _entry("2010-01-01", "2010-03-31", 200, 2010, "Q1", "10-Q", "2010-05-01"),
                ]}},
            }
        }
    }
    quarters = edgar.build_quarters(companyfacts)

    assert "2009-Q1" not in quarters
    assert "2010-Q1" in quarters


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
