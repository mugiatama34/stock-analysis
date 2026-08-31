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


def test_instant_chain_resolves_per_quarter_independently():
    # LongTermDebtNoncurrent ve LongTermDebt ayni kavramin ALTERNATIF
    # etiketleridir (bkz. config.INSTANT_METRICS 'chain' modu aciklamasi).
    # Gercek AAPL deseni: sirket 2015-Q1/Q2'de gecici olarak
    # LongTermDebtNoncurrent yerine LongTermDebt kullanmis - bu XBRL
    # hazirlayici tutarsizligidir, gercek tanim degisikligi degil. Zincir
    # HER CEYREK icin bagimsiz cozulmeli: sirket genelinde tek etikete
    # kilitlenip diger ceyregin gercekten var olan verisini "veri yok"
    # gostermemeli.
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
    resolved = edgar._resolve_instant_metric(
        companyfacts, {"mode": "chain", "tags": ["LongTermDebtNoncurrent", "LongTermDebt"]}, wanted
    )

    assert resolved["2022-12-31"] == {"val": 500, "tag": "LongTermDebtNoncurrent"}
    assert resolved["2023-03-31"] == {"val": 600, "tag": "LongTermDebt"}


def test_instant_chain_prefers_priority_tag_when_both_report_same_quarter():
    # Ayni ceyrek icin HER IKI etikette de veri varsa, listede once gelen
    # (oncelikli) etiket kazanmali - duration metriklerdeki etiket
    # onceligiyle tutarli (bkz. _dedupe_entries).
    companyfacts = {
        "facts": {
            "us-gaap": {
                "LongTermDebtNoncurrent": {"units": {"USD": [
                    _instant("2023-03-31", 500, "10-Q", "2023-05-01"),
                ]}},
                "LongTermDebt": {"units": {"USD": [
                    _instant("2023-03-31", 999, "10-Q", "2023-05-01"),
                ]}},
            }
        }
    }
    resolved = edgar._resolve_instant_metric(
        companyfacts, {"mode": "chain", "tags": ["LongTermDebtNoncurrent", "LongTermDebt"]}, {"2023-03-31"}
    )

    assert resolved["2023-03-31"] == {"val": 500, "tag": "LongTermDebtNoncurrent"}


def test_instant_chain_subtracts_current_portion_to_avoid_double_count():
    # F/GM deseni: sirket bu ceyrek icin LongTermDebtNoncurrent yerine
    # LongTermDebt kullanmis (zincirin yedek etiketi) VE ayni ceyrekte
    # LongTermDebtCurrent (short_term_debt'in bir bileseni) de raporlanmis.
    # LongTermDebt US-GAAP'ta cari kismi ZATEN icerir - fark alinmazsa cari
    # kisim total_debt'te iki kez sayilir (bkz. config.py long_term_debt
    # subtract_when_using aciklamasi).
    companyfacts = {
        "facts": {
            "us-gaap": {
                "LongTermDebt": {"units": {"USD": [
                    _instant("2023-03-31", 1000, "10-Q", "2023-05-01"),
                ]}},
                "LongTermDebtCurrent": {"units": {"USD": [
                    _instant("2023-03-31", 150, "10-Q", "2023-05-01"),
                ]}},
            }
        }
    }
    resolved = edgar._resolve_instant_metric(
        companyfacts,
        {
            "mode": "chain",
            "tags": ["LongTermDebtNoncurrent", "LongTermDebt"],
            "subtract_when_using": {"LongTermDebt": "LongTermDebtCurrent"},
        },
        {"2023-03-31"},
    )

    # 1000 - 150 = 850: artik LongTermDebtNoncurrent ile ayni kapsamda.
    assert resolved["2023-03-31"] == {"val": 850, "tag": "LongTermDebt"}


def test_instant_chain_subtract_noop_when_current_portion_absent():
    # AAPL 2015 deseni: LongTermDebt kullanildi ama LongTermDebtCurrent o
    # ceyrek icin hic raporlanmamis (sirketin cari vadeli borcu yok) -
    # cikaracak bir sey olmadigi icin deger degismemeli.
    companyfacts = {
        "facts": {
            "us-gaap": {
                "LongTermDebt": {"units": {"USD": [
                    _instant("2015-03-28", 1000, "10-Q", "2015-05-01"),
                ]}},
            }
        }
    }
    resolved = edgar._resolve_instant_metric(
        companyfacts,
        {
            "mode": "chain",
            "tags": ["LongTermDebtNoncurrent", "LongTermDebt"],
            "subtract_when_using": {"LongTermDebt": "LongTermDebtCurrent"},
        },
        {"2015-03-28"},
    )

    assert resolved["2015-03-28"] == {"val": 1000, "tag": "LongTermDebt"}


def test_instant_chain_subtract_does_not_apply_to_primary_tag():
    # subtract_when_using SADECE haritada belirtilen etikete (yedek) uygulanir
    # - zincirin birincil etiketi (LongTermDebtNoncurrent) zaten cari kismi
    # HARIC TUTTUGU icin cikarma islemi uygulanmamali.
    companyfacts = {
        "facts": {
            "us-gaap": {
                "LongTermDebtNoncurrent": {"units": {"USD": [
                    _instant("2023-03-31", 500, "10-Q", "2023-05-01"),
                ]}},
                "LongTermDebtCurrent": {"units": {"USD": [
                    _instant("2023-03-31", 150, "10-Q", "2023-05-01"),
                ]}},
            }
        }
    }
    resolved = edgar._resolve_instant_metric(
        companyfacts,
        {
            "mode": "chain",
            "tags": ["LongTermDebtNoncurrent", "LongTermDebt"],
            "subtract_when_using": {"LongTermDebt": "LongTermDebtCurrent"},
        },
        {"2023-03-31"},
    )

    assert resolved["2023-03-31"] == {"val": 500, "tag": "LongTermDebtNoncurrent"}


def test_chain_with_fallback_uses_direct_single_piece_tag_when_available():
    # total_debt deseni (bkz. config.INSTANT_METRICS): sirket tek parca bir
    # toplam borc etiketi (DebtAndCapitalLeaseObligations) raporlamissa bu
    # DOGRUDAN kullanilmali - short_term_debt/long_term_debt bilesenlerinin
    # zaten cozulmus (ve BILEREK cok farkli) degerlerine hic bakilmamali.
    companyfacts = {
        "facts": {
            "us-gaap": {
                "DebtAndCapitalLeaseObligations": {"units": {"USD": [
                    _instant("2023-03-31", 700, "10-Q", "2023-05-01"),
                ]}},
            }
        }
    }
    resolved_so_far = {
        "short_term_debt": {"2023-03-31": {"val": 111, "tag": "DebtCurrent"}},
        "long_term_debt": {"2023-03-31": {"val": 222, "tag": "LongTermDebtNoncurrent"}},
    }
    resolved = edgar._resolve_instant_chain_with_fallback(
        companyfacts,
        ["DebtAndCapitalLeaseObligations", "DebtLongtermAndShorttermCombinedAmount"],
        {"2023-03-31"},
        ["short_term_debt", "long_term_debt"],
        resolved_so_far,
    )

    assert resolved["2023-03-31"] == {"val": 700, "tag": "DebtAndCapitalLeaseObligations"}


def test_chain_with_fallback_first_tag_wins_when_both_direct_tags_present():
    companyfacts = {
        "facts": {
            "us-gaap": {
                "DebtAndCapitalLeaseObligations": {"units": {"USD": [
                    _instant("2023-03-31", 700, "10-Q", "2023-05-01"),
                ]}},
                "DebtLongtermAndShorttermCombinedAmount": {"units": {"USD": [
                    _instant("2023-03-31", 999, "10-Q", "2023-05-01"),
                ]}},
            }
        }
    }
    resolved = edgar._resolve_instant_chain_with_fallback(
        companyfacts,
        ["DebtAndCapitalLeaseObligations", "DebtLongtermAndShorttermCombinedAmount"],
        {"2023-03-31"},
        ["short_term_debt", "long_term_debt"],
        {},
    )

    assert resolved["2023-03-31"] == {"val": 700, "tag": "DebtAndCapitalLeaseObligations"}


def test_chain_with_fallback_sums_components_when_no_direct_tag_reported():
    # Sirket hicbir tek-parca toplam borc etiketi raporlamamis (AAPL/F
    # deseni) - short_term_debt + long_term_debt'in ONCEDEN cozulmus
    # degerlerine dusulmeli, tag "short_term_debt+long_term_debt" olarak
    # isaretlenmeli (bkz. config.INSTANT_METRICS total_debt aciklamasi).
    companyfacts = {"facts": {"us-gaap": {}}}
    resolved_so_far = {
        "short_term_debt": {"2023-03-31": {"val": 100, "tag": "DebtCurrent"}},
        "long_term_debt": {"2023-03-31": {"val": 4800, "tag": "LongTermDebt"}},
    }
    resolved = edgar._resolve_instant_chain_with_fallback(
        companyfacts,
        ["DebtAndCapitalLeaseObligations", "DebtLongtermAndShorttermCombinedAmount"],
        {"2023-03-31"},
        ["short_term_debt", "long_term_debt"],
        resolved_so_far,
    )

    assert resolved["2023-03-31"] == {"val": 4900, "tag": "short_term_debt+long_term_debt"}


def test_chain_with_fallback_sum_treats_missing_component_as_absent_not_error():
    # Sadece long_term_debt cozulmus, short_term_debt bu ceyrek icin hic
    # veri dondurmemis - fallback toplaminda eksik bilesen 0 sayilir
    # (mevcut short_term_debt + long_term_debt davranisiyla tutarli).
    companyfacts = {"facts": {"us-gaap": {}}}
    resolved_so_far = {
        "long_term_debt": {"2023-03-31": {"val": 4800, "tag": "LongTermDebt"}},
    }
    resolved = edgar._resolve_instant_chain_with_fallback(
        companyfacts,
        ["DebtAndCapitalLeaseObligations", "DebtLongtermAndShorttermCombinedAmount"],
        {"2023-03-31"},
        ["short_term_debt", "long_term_debt"],
        resolved_so_far,
    )

    assert resolved["2023-03-31"] == {"val": 4800, "tag": "long_term_debt"}


def test_load_fact_entries_falls_back_to_non_us_gaap_namespace():
    # Ford teshisi: bir filer standart gorunumlu bir kavrami (burada
    # DebtAndCapitalLeaseObligations) us-gaap yerine kendi ozel taksonomi
    # namespace'inde ("f", ticker'a dayali extension namespace) ayni yerel
    # isimle raporlayabiliyor. companyfacts bunu ISME degil NAMESPACE'E
    # gore gruplar - sadece 'us-gaap' icine bakmak, deger companyfacts'te
    # GERCEKTEN dururken hic bulunamamasina yol aciyordu.
    companyfacts = {
        "facts": {
            "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": []}}},
            "f": {
                "DebtAndCapitalLeaseObligations": {
                    "units": {"USD": [_instant("2023-03-31", 5300, "10-Q", "2023-05-01")]}
                }
            },
        }
    }
    entries = edgar._load_fact_entries(companyfacts, "DebtAndCapitalLeaseObligations")
    assert entries == [_instant("2023-03-31", 5300, "10-Q", "2023-05-01")]


def test_load_fact_entries_prefers_us_gaap_over_other_namespace():
    # Ayni yerel isim HEM us-gaap'te HEM baska bir namespace'te varsa,
    # standart (us-gaap) her zaman kazanmali - extension namespace'ler
    # sadece us-gaap'te hic yoksa devreye girer.
    companyfacts = {
        "facts": {
            "us-gaap": {
                "DebtAndCapitalLeaseObligations": {
                    "units": {"USD": [_instant("2023-03-31", 700, "10-Q", "2023-05-01")]}
                }
            },
            "f": {
                "DebtAndCapitalLeaseObligations": {
                    "units": {"USD": [_instant("2023-03-31", 999, "10-Q", "2023-05-01")]}
                }
            },
        }
    }
    entries = edgar._load_fact_entries(companyfacts, "DebtAndCapitalLeaseObligations")
    assert entries == [_instant("2023-03-31", 700, "10-Q", "2023-05-01")]


def test_chain_with_fallback_leaves_quarter_empty_when_neither_path_has_data():
    companyfacts = {"facts": {"us-gaap": {}}}
    resolved = edgar._resolve_instant_chain_with_fallback(
        companyfacts,
        ["DebtAndCapitalLeaseObligations", "DebtLongtermAndShorttermCombinedAmount"],
        {"2023-03-31"},
        ["short_term_debt", "long_term_debt"],
        {},
    )

    assert "2023-03-31" not in resolved


def test_build_quarters_total_debt_falls_back_to_short_plus_long_term_debt():
    # Uctan uca: hicbir tek-parca toplam borc etiketi yok, sadece
    # short_term_debt/long_term_debt bilesenleri var - total_debt bunlarin
    # toplamina dusmeli ve yolu "tag" alaninda isaretlemeli.
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
                "DebtCurrent": {"units": {"USD": [
                    _instant("2023-03-31", 100, "10-Q", "2023-05-01"),
                ]}},
                "LongTermDebtNoncurrent": {"units": {"USD": [
                    _instant("2023-03-31", 4800, "10-Q", "2023-05-01"),
                ]}},
            }
        }
    }
    quarters = edgar.build_quarters(companyfacts)
    q = quarters["2023-Q1"]

    assert q["metrics"]["total_debt"]["value"] == 4900
    assert q["metrics"]["total_debt"]["tag"] == "short_term_debt+long_term_debt"


def test_build_quarters_total_debt_uses_direct_tag_over_component_sum():
    # DebtAndCapitalLeaseObligations raporlanmissa (kiralama yukumluluklerini
    # de icerir) DOGRUDAN kullanilmali - short_term_debt/long_term_debt
    # toplamina (farkli kapsam) DUSULMEMELI.
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
                "DebtCurrent": {"units": {"USD": [
                    _instant("2023-03-31", 100, "10-Q", "2023-05-01"),
                ]}},
                "LongTermDebtNoncurrent": {"units": {"USD": [
                    _instant("2023-03-31", 4800, "10-Q", "2023-05-01"),
                ]}},
                "DebtAndCapitalLeaseObligations": {"units": {"USD": [
                    _instant("2023-03-31", 5300, "10-Q", "2023-05-01"),
                ]}},
            }
        }
    }
    quarters = edgar.build_quarters(companyfacts)
    q = quarters["2023-Q1"]

    assert q["metrics"]["total_debt"]["value"] == 5300
    assert q["metrics"]["total_debt"]["tag"] == "DebtAndCapitalLeaseObligations"


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


def test_multi_year_continuous_discrete_chain_resolves_every_fiscal_year():
    # Gercek AAPL deseni: sirket HER ceyregi ayrik raporluyor ve bir mali
    # yilin Q4'u, bir sonrakinin Q1'ine HICBIR BOSLUK BIRAKMADAN baglaniyor
    # (Q4 bitisi + 1 gun = sonraki Q1 baslangici) - iki mali yil boyunca
    # kesintisiz bir zincir. Sadece "oncesinde ceyrek yoksa capadir" testi
    # kullanilsaydi tek bir capa bulunur ve SADECE ILK 4 ceyrek islenir,
    # ikinci yil tamamen kaybolurdu. Yillik (10-K) kayitlar iki ayri capayi
    # dogru sekilde isaretlemeli.
    entries = [
        # FY2022: 2022-01-01 .. 2022-12-31
        _entry("2022-01-01", "2022-03-31", 100, 2022, "Q1", "10-Q", "2022-05-01"),
        _entry("2022-04-01", "2022-06-30", 110, 2022, "Q2", "10-Q", "2022-08-01"),
        _entry("2022-07-01", "2022-09-30", 120, 2022, "Q3", "10-Q", "2022-11-01"),
        _entry("2022-01-01", "2022-12-31", 460, 2022, "FY", "10-K", "2023-02-01"),
        # FY2023: 2023-01-01 .. 2023-12-31, hicbir bosluk olmadan devam ediyor
        _entry("2023-01-01", "2023-03-31", 130, 2023, "Q1", "10-Q", "2023-05-01"),
        _entry("2023-04-01", "2023-06-30", 140, 2023, "Q2", "10-Q", "2023-08-01"),
        _entry("2023-07-01", "2023-09-30", 150, 2023, "Q3", "10-Q", "2023-11-01"),
        _entry("2023-01-01", "2023-12-31", 580, 2023, "FY", "10-K", "2024-02-01"),
    ]
    result = resolve_duration_quarters(entries)

    assert result[(2022, "Q1")]["value"] == 100
    assert result[(2022, "Q4")]["value"] == 130  # 460 - (100+110+120)
    assert result[(2023, "Q1")]["value"] == 130
    assert result[(2023, "Q2")]["value"] == 140
    assert result[(2023, "Q3")]["value"] == 150
    assert result[(2023, "Q4")]["value"] == 160  # 580 - (130+140+150)


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


def test_build_quarters_normalizes_diluted_shares_and_eps_for_later_split():
    # Gercek AAPL deseninde gozlemlenen hata: Q1-Q3, bolunmeden ONCE filed
    # olmus orijinal 10-Q'lardan gelir (kucuk/eski hisse tabani); yillik
    # (_annual) kayit ise bolunmeden SONRA filed olmus bir 10-K'nin
    # karsilastirma tablosundan gelir ve GAAP geregi bolunme-duzeltilmis
    # (buyuk/yeni hisse tabani) raporlanir. Normalize edilmeden Q4 eps =
    # yillik eps - (Q1+Q2+Q3 eps) taban karisikligi yuzunden anlamsiz buyuk
    # negatif bir deger uretiyordu. splits verildiginde tum diluted_shares
    # bugunku (bolunme sonrasi) tabana getirilmeli.
    companyfacts = {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {"units": {"USD": [
                    _entry("2012-01-01", "2012-03-31", 1000, 2012, "Q1", "10-Q", "2012-05-01"),
                    _entry("2012-04-01", "2012-06-30", 1000, 2012, "Q2", "10-Q", "2012-08-01"),
                    _entry("2012-07-01", "2012-09-30", 1000, 2012, "Q3", "10-Q", "2012-11-01"),
                    _entry("2012-01-01", "2012-12-31", 4000, 2012, "FY", "10-K", "2013-02-01"),
                ]}},
                "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [
                    # Q1-Q3: bolunmeden (2014-06-01, 7:1) ONCE filed - eski (kucuk) taban.
                    _entry("2012-01-01", "2012-03-31", 100, 2012, "Q1", "10-Q", "2012-05-01"),
                    _entry("2012-04-01", "2012-06-30", 100, 2012, "Q2", "10-Q", "2012-08-01"),
                    _entry("2012-07-01", "2012-09-30", 100, 2012, "Q3", "10-Q", "2012-11-01"),
                    # Yillik: bolunmeden SONRA filed - GAAP geregi zaten
                    # bolunme-duzeltilmis (700 = 100*7) raporlanmis.
                    _entry("2012-01-01", "2012-12-31", 700, 2012, "FY", "10-K", "2014-11-01"),
                ]}},
            }
        }
    }
    splits = [{"date": "2014-06-01", "ratio": 7.0}]

    normalized = edgar.build_quarters(companyfacts, splits=splits)
    without_normalization = edgar.build_quarters(companyfacts)

    # Q1-Q3 filed tarihinden sonra bolunme oldugu icin 7x buyutulmeli.
    assert normalized["2012-Q1"]["metrics"]["diluted_shares"]["value"] == 700
    assert normalized["2012-Q1"]["metrics"]["eps_diluted"]["value"] == 1000 / 700

    # Yillik kayit filed tarihinden sonra bolunme olmadigi icin degismemeli.
    q4 = normalized["2012-Q4"]
    q1_eps = normalized["2012-Q1"]["metrics"]["eps_diluted"]["value"]
    annual_eps = 4000 / 700
    assert q4["metrics"]["eps_diluted"]["value"] == annual_eps - 3 * q1_eps
    assert q4["metrics"]["eps_diluted"]["value"] > 0

    # Normalize edilmeden (eski davranis) taban karisikligi yuzunden Q4
    # eps buyuk negatif cikiyordu - regresyonu somutlastirmak icin.
    assert without_normalization["2012-Q4"]["metrics"]["eps_diluted"]["value"] < -10


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


def test_sum_component_used_when_other_components_missing_for_period():
    # Gercek AAPL verisinde gozlemlendi: bazi ceyreklerde short_term_debt'in
    # bilesenlerinden (ShortTermBorrowings/DebtCurrent/LongTermDebtCurrent)
    # hicbiri o donem icin veri dondurmuyor, ama CommercialPaper doluyor.
    # Bilesenler birbirine BAGIMLI olmamali - digerleri o ceyrekte yoksa 0
    # sayilip sadece bulunan bilesenin degeri kullanilmali (bkz.
    # config.INSTANT_METRICS 'sum' modu aciklamasi).
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
                # DebtCurrent (primary) ve ShortTermBorrowings/LongTermDebtCurrent
                # (diger bilesenler) hicbiri bu ceyrek icin veri dondurmuyor.
                "CommercialPaper": {"units": {"USD": [
                    _instant("2023-03-31", 30, "10-Q", "2023-05-01"),
                ]}},
            }
        }
    }
    quarters = edgar.build_quarters(companyfacts)
    q = quarters["2023-Q1"]

    assert q["metrics"]["short_term_debt"]["value"] == 30
    assert q["metrics"]["short_term_debt"]["tag"] == "CommercialPaper"


def test_sum_primary_tag_used_alone_ignoring_components():
    # DebtCurrent (primary) TEK BASINA zaten toplam bir kalemdir - o ceyrek
    # icin veri donduruyorsa, ayni ceyrekte CommercialPaper gibi bir bilesen
    # de raporlanmis olsa bile ikisi toplanmamali (cift sayim). Sadece
    # primary kullanilmali (bkz. config.INSTANT_METRICS 'sum' modu
    # aciklamasi).
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
                "DebtCurrent": {"units": {"USD": [
                    _instant("2023-03-31", 90, "10-Q", "2023-05-01"),
                ]}},
                "CommercialPaper": {"units": {"USD": [
                    _instant("2023-03-31", 30, "10-Q", "2023-05-01"),
                ]}},
            }
        }
    }
    quarters = edgar.build_quarters(companyfacts)
    q = quarters["2023-Q1"]

    assert q["metrics"]["short_term_debt"]["value"] == 90
    assert q["metrics"]["short_term_debt"]["tag"] == "DebtCurrent"


def test_build_quarters_avoids_double_counting_current_portion_of_long_term_debt():
    # F/GM deseni uctan uca: LongTermDebtNoncurrent raporlanmamis (zincir
    # yedek etikete, LongTermDebt'e dusuyor), ayni ceyrekte hem
    # LongTermDebtCurrent (short_term_debt bileseni) hem de DebtCurrent
    # (short_term_debt primary'si) da var. Fark alinmazsa cari kisim
    # (200) hem short_term_debt'te hem long_term_debt'te sayilir ve
    # total_debt sismis cikar. Bu, gercek config.INSTANT_METRICS
    # (subtract_when_using dahil) ile calisir - custom spec verilmez.
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
                "LongTermDebtCurrent": {"units": {"USD": [
                    _instant("2023-03-31", 200, "10-Q", "2023-05-01"),
                ]}},
                "LongTermDebt": {"units": {"USD": [
                    _instant("2023-03-31", 5000, "10-Q", "2023-05-01"),
                ]}},
            }
        }
    }
    quarters = edgar.build_quarters(companyfacts)
    q = quarters["2023-Q1"]

    # short_term_debt: primary (DebtCurrent) yok, bilesen LongTermDebtCurrent=200.
    assert q["metrics"]["short_term_debt"]["value"] == 200
    # long_term_debt: LongTermDebt (5000) - LongTermDebtCurrent (200) = 4800.
    assert q["metrics"]["long_term_debt"]["value"] == 4800
    assert q["metrics"]["long_term_debt"]["tag"] == "LongTermDebt"
    assert q["metrics"]["short_term_debt"]["tag"] == "LongTermDebtCurrent"
