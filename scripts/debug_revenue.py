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


if __name__ == "__main__":
    main()
