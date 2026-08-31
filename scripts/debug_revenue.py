import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_analysis import config, edgar  # noqa: E402


def main():
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    cik = edgar.get_cik(ticker)
    companyfacts = edgar.fetch_companyfacts(cik)

    print("=== HAM ETIKET VERISI (revenue adaylari) ===")
    for tag in config.DURATION_TAG_PRIORITIES["revenue"]:
        raw = edgar._load_fact_entries(companyfacts, tag)
        filed = [e for e in raw if e.get("form", "").startswith(("10-Q", "10-K"))]
        no_fy_fp = [e for e in filed if e.get("fy") is None or e.get("fp") is None]
        print(f"{tag}: toplam={len(raw)} 10-Q/10-K={len(filed)} fy/fp-eksik={len(no_fy_fp)}")
        if no_fy_fp:
            for e in no_fy_fp[:5]:
                print("    fy/fp eksik ornek:", {k: e.get(k) for k in ("start", "end", "val", "fy", "fp", "form", "filed")})

    print()
    print("=== CostOfGoodsAndServicesSold (68/68 dolu referans) vs Revenues zinciri kiyaslamasi ===")
    cost_raw = edgar._load_fact_entries(companyfacts, "CostOfGoodsAndServicesSold")
    cost_resolved = edgar.resolve_duration_quarters(cost_raw)
    all_qkeys = sorted(cost_resolved.keys())
    print(f"Referans (cost_of_revenue) ceyrek sayisi: {len(all_qkeys)}")

    rev_combined = edgar._load_priority_entries(companyfacts, config.DURATION_TAG_PRIORITIES["revenue"])
    rev_resolved = edgar.resolve_duration_quarters(rev_combined)

    missing = [qk for qk in all_qkeys if qk not in rev_resolved]
    print(f"revenue icin eksik ceyrek sayisi: {len(missing)}")
    print("Eksik ceyrekler (fy,fp):", missing)

    print()
    print("=== Eksik ceyreklerden birkacinin ham verisi (tum adaylarda) ===")
    for fy, fp in missing[:6]:
        print(f"-- {fy}-{fp} --")
        ref_end = cost_resolved[(fy, fp)]["end"]
        print("   referans period_end:", ref_end)
        for tag in config.DURATION_TAG_PRIORITIES["revenue"]:
            raw = edgar._load_fact_entries(companyfacts, tag)
            matches = [e for e in raw if e.get("end") == ref_end]
            for e in matches:
                print(f"   [{tag}]", {k: e.get(k) for k in ("start", "end", "val", "fy", "fp", "form", "filed")})

    print()
    print("=== ANCHOR ICI DURUM (quarter_by_start / known_quarter_ends) ===")
    filed_entries = [
        e for e in rev_combined
        if (e.get("form", "").startswith("10-Q") or e.get("form", "").startswith("10-K"))
        and "start" in e and "end" in e
    ]
    value_entries = edgar._dedupe_entries(filed_entries)
    quarter_by_start, half_by_start, three_q_by_start, annual_by_start = {}, {}, {}, {}
    for e in value_entries:
        kind = edgar._classify_duration(edgar._days(e))
        if kind == "quarter":
            quarter_by_start[e["start"]] = e
        elif kind == "half":
            half_by_start[e["start"]] = e
        elif kind == "three_q":
            three_q_by_start[e["start"]] = e
        elif kind == "annual":
            annual_by_start[e["start"]] = e
    known_quarter_ends = {e["end"] for e in quarter_by_start.values()}

    print(f"quarter_by_start eleman sayisi: {len(quarter_by_start)}")
    print(f"half_by_start eleman sayisi: {len(half_by_start)}")
    print(f"three_q_by_start eleman sayisi: {len(three_q_by_start)}")
    print(f"annual_by_start eleman sayisi: {len(annual_by_start)}")

    print()
    print("-- 2010-09-26 (2011-Q1'in beklenen capasi) analiz --")
    s = "2010-09-26"
    if s in quarter_by_start:
        e = quarter_by_start[s]
        print("   quarter_by_start icinde VAR:", {k: e.get(k) for k in ("start", "end", "val", "filed", "_tag")})
        prev = edgar._prev_day(s)
        print(f"   _prev_day({s}) = {prev}")
        print(f"   {prev} known_quarter_ends icinde mi: {prev in known_quarter_ends}")
        if prev in known_quarter_ends:
            culprit = [e2 for e2 in quarter_by_start.values() if e2["end"] == prev]
            for c in culprit:
                print("   BU BITISE SAHIP CEYREK (capayi engelleyen):", {k: c.get(k) for k in ("start", "end", "val", "filed", "_tag")})
    else:
        print("   quarter_by_start icinde YOK (siniflandirma sirasinda kaybolmus)")

    print()
    print("-- Tum quarter_by_start start tarihleri (sirali, ilk 40) --")
    for s in sorted(quarter_by_start)[:40]:
        e = quarter_by_start[s]
        prev = edgar._prev_day(s)
        anchor = prev not in known_quarter_ends
        print(f"   start={s} end={e['end']} val={e['val']} tag={e.get('_tag')} ANCHOR={anchor}")


if __name__ == "__main__":
    main()
