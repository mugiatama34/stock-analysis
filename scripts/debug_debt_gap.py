import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_analysis import config, edgar, pipeline  # noqa: E402


def main():
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    data = pipeline.fetch_stock_data(ticker)
    quarters = data["quarters"]
    companyfacts = edgar.fetch_companyfacts(data["cik"])
    all_ends = {q["period_end"] for q in quarters.values() if q.get("period_end")}

    for metric in ("short_term_debt", "long_term_debt"):
        tags = config.INSTANT_TAG_PRIORITIES[metric]
        used_tag, _ = edgar._resolve_instant_metric(companyfacts, tags, all_ends)
        print(f"=== {metric} - sirket genelinde secilen (sabit) etiket: {used_tag} ===")

        empty_qs = sorted(
            (
                (qk, q)
                for qk, q in quarters.items()
                if q.get("period_end") and q["metrics"][metric]["value"] is None
            ),
            key=lambda kv: kv[1]["period_end"],
        )
        print(f"bos ceyrek sayisi: {len(empty_qs)}")
        for qk, q in empty_qs:
            pe = q["period_end"]
            print(f"-- {qk} (period_end={pe}) --")
            for tag in tags:
                raw = edgar._load_fact_entries(companyfacts, tag)
                for e in raw:
                    if e.get("end") == pe:
                        print(f"   [{tag}]", {k: e.get(k) for k in ("end", "val", "form", "filed")})
        print()


if __name__ == "__main__":
    main()
