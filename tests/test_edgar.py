import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_analysis.edgar import resolve_duration_quarters


def _entry(start, end, val, fy, fp, form, filed):
    return {"start": start, "end": end, "val": val, "fy": fy, "fp": fp, "form": form, "filed": filed}


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
