import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_analysis import config, edgar, pipeline  # noqa: E402

TICKER = "AAPL"


def dump_raw_tag(companyfacts, tag, ends=None):
    entries = edgar._load_fact_entries(companyfacts, tag)
    print(f"--- ham etiket: {tag} (toplam {len(entries)} kayit) ---")
    if not entries:
        print("  (companyfacts'te bu etiket hic yok)")
        return
    filed = [e for e in entries if e.get("form", "").startswith(("10-Q", "10-K"))]
    shown = filed if ends is None else [e for e in filed if e.get("end") in ends]
    for e in sorted(shown, key=lambda e: (e.get("end", ""), e.get("filed", ""))):
        print(
            f"  end={e.get('end')} start={e.get('start')} val={e.get('val')} "
            f"form={e.get('form')} filed={e.get('filed')} fy={e.get('fy')} fp={e.get('fp')}"
        )
    if ends is not None and not shown:
        print(f"  (filed 10-Q/10-K kayitlari icinde istenen end tarihleriyle {ends} eslesen yok)")


def main():
    cik = edgar.get_cik(TICKER)
    companyfacts = edgar.fetch_companyfacts(cik)

    print("=" * 70)
    print("2) CommercialPaper ham veri kontrolu")
    print("=" * 70)
    for tag in ["CommercialPaper", "ShortTermBorrowings", "DebtCurrent", "LongTermDebtCurrent"]:
        dump_raw_tag(companyfacts, tag)

    data = pipeline.fetch_stock_data(TICKER)
    quarters = data["quarters"]

    q2015_q1 = quarters.get("2015-Q1")
    q2015_q2 = quarters.get("2015-Q2")
    ends_2015 = {
        q["period_end"] for q in (q2015_q1, q2015_q2) if q and q.get("period_end")
    }

    print()
    print("=" * 70)
    print(f"3) 2015-Q1/Q2 borc bosluğu - period_end tarihleri: {sorted(ends_2015)}")
    print("=" * 70)
    for tag in [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        "ShortTermBorrowings",
        "DebtCurrent",
        "LongTermDebtCurrent",
        "CommercialPaper",
    ]:
        dump_raw_tag(companyfacts, tag, ends=ends_2015)

    print()
    print(
        "pipeline sonucu 2015-Q1 short_term_debt:",
        q2015_q1["metrics"]["short_term_debt"] if q2015_q1 else None,
    )
    print(
        "pipeline sonucu 2015-Q1 long_term_debt:",
        q2015_q1["metrics"]["long_term_debt"] if q2015_q1 else None,
    )
    print(
        "pipeline sonucu 2015-Q2 short_term_debt:",
        q2015_q2["metrics"]["short_term_debt"] if q2015_q2 else None,
    )
    print(
        "pipeline sonucu 2015-Q2 long_term_debt:",
        q2015_q2["metrics"]["long_term_debt"] if q2015_q2 else None,
    )

    print()
    print("=" * 70)
    print("1) Tum Q4 eps_diluted degerleri + ttm.eps_diluted + valuation.pe")
    print("=" * 70)
    for qkey in sorted(quarters):
        q = quarters[qkey]
        if q.get("fiscal_quarter") == 4:
            eps = q["metrics"]["eps_diluted"]["value"]
            print(f"  {qkey}: eps_diluted = {eps}")

    ttm = data.get("ttm", {})
    valuation = data.get("valuation", {})
    print()
    print("ttm.eps_diluted:", ttm.get("eps_diluted") if ttm.get("available") else f"veri yok ({ttm.get('reason')})")
    print("valuation.pe:", valuation.get("pe") if valuation.get("available") else f"veri yok ({valuation.get('reason')})")


if __name__ == "__main__":
    main()
