import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_analysis import config, errors, pipeline  # noqa: E402

# Ceyrek sozluklerinde ("quarters[qkey]['metrics']") bulunan tum metrikler.
# eps_diluted config'teki etiket zincirlerinde yok (artik hesaplaniyor,
# bkz. edgar.build_quarters) ama quarter["metrics"] icinde hala bir anahtar
# olarak var, bu yuzden ayrica eklenir.
_QUARTER_METRICS = list(config.DURATION_TAG_PRIORITIES) + list(config.INSTANT_TAG_PRIORITIES) + [
    "eps_diluted",
]


def summarize(data: dict) -> dict:
    """Cekilen veriden, her metrik icin kac ceyrekte deger bulundugunu, hangi
    EDGAR etiketinin eslestigini, ilk/son dolu ceyregi ve bu iki ceyrek
    ARASINDAKI (seri ici) bosluk sayisini cikaran bir ozet uretir. Sadece
    dolu/veriyok adedi tek basina yeterli degil: bir metrik "180 dolu, 20
    veri yok" gorunse de o 20'si bastan mi (seri henuz baslamamis, sorun
    degil) yoksa ortada bir bosluk mu (gercek veri kaybi) belli olmaz."""
    quarters = data["quarters"]
    ordered = sorted(
        ((qkey, q) for qkey, q in quarters.items() if q.get("period_end")),
        key=lambda kv: kv[1]["period_end"],
    )

    metrics_summary = {}
    for metric in _QUARTER_METRICS:
        filled = 0
        missing = 0
        tags_used = Counter()
        flags = []
        for qkey, quarter in ordered:
            entry = quarter["metrics"].get(metric, {})
            has_value = entry.get("value") is not None
            flags.append((qkey, has_value))
            if has_value:
                filled += 1
                if entry.get("tag"):
                    tags_used[entry["tag"]] += 1
            else:
                missing += 1

        filled_positions = [i for i, (_, has) in enumerate(flags) if has]
        if filled_positions:
            first_idx, last_idx = filled_positions[0], filled_positions[-1]
            first_filled_quarter = flags[first_idx][0]
            last_filled_quarter = flags[last_idx][0]
            internal_gap_quarters = sum(1 for _, has in flags[first_idx:last_idx + 1] if not has)
        else:
            first_filled_quarter = None
            last_filled_quarter = None
            internal_gap_quarters = 0

        metrics_summary[metric] = {
            "filled_quarters": filled,
            "missing_quarters": missing,
            "tags_used": dict(tags_used),
            "first_filled_quarter": first_filled_quarter,
            "last_filled_quarter": last_filled_quarter,
            "internal_gap_quarters": internal_gap_quarters,
        }

    return {
        "quarter_count": len(quarters),
        "metrics": metrics_summary,
    }


def print_report(ticker: str, data: dict, summary: dict) -> None:
    print("=" * 70)
    print(f"VERI KATMANI DOGRULAMA RAPORU - {ticker}")
    print("=" * 70)
    print(f"Sirket adi : {data.get('company_name')}")
    print(f"CIK        : {data.get('cik')}")
    print(f"Sektor     : {data.get('sector')} / {data.get('industry')}")
    print(f"Bulunan ceyrek sayisi: {summary['quarter_count']}")
    print()

    header = (
        f"{'Metrik':<28}{'Dolu':>6}{'VeriYok':>9}{'IlkCeyrek':>12}"
        f"{'SonCeyrek':>12}{'SeriIciBosluk':>15}   Eslesen EDGAR etiket(ler)i"
    )
    print(header)
    print("-" * len(header))
    for metric, info in summary["metrics"].items():
        if info["tags_used"]:
            tags_str = ", ".join(
                f"{tag} ({count} ceyrek)" for tag, count in info["tags_used"].items()
            )
        else:
            tags_str = "(hicbir aday etiket eslesmedi)"
        first_q = info["first_filled_quarter"] or "-"
        last_q = info["last_filled_quarter"] or "-"
        gap_marker = " <-- BOSLUK VAR" if info["internal_gap_quarters"] else ""
        print(
            f"{metric:<28}{info['filled_quarters']:>6}{info['missing_quarters']:>9}"
            f"{first_q:>12}{last_q:>12}{info['internal_gap_quarters']:>15}"
            f"   {tags_str}{gap_marker}"
        )
    print()

    ttm = data.get("ttm", {})
    quarters = data.get("quarters", {})
    latest_period_end = max(
        (q["period_end"] for q in quarters.values() if q.get("period_end")), default=None
    )
    if ttm.get("available"):
        print(f"TTM: mevcut - donem sonu {ttm.get('period_end')}")
        if latest_period_end and ttm.get("period_end") != latest_period_end:
            print(
                f"  UYARI: TTM donem sonu ({ttm.get('period_end')}) en son bulunan "
                f"ceyregin donem sonundan ({latest_period_end}) farkli."
            )
    else:
        print(f"TTM: veri yok - {ttm.get('reason')}")

    valuation = data.get("valuation", {})
    if valuation.get("available"):
        print("Degerleme oranlari (P/E, P/S, EV/EBITDA, P/FCF): mevcut")
    else:
        print(f"Degerleme oranlari: veri yok - {valuation.get('reason')}")

    sector_flag = data.get("sector_flag", {})
    if sector_flag.get("is_financial_sector"):
        print(f"Sektor istisnasi: {sector_flag.get('reason')}")

    peers = data.get("peers", {})
    if peers.get("status") != "ok":
        print(f"Rakipler: veri alinamadi - {peers.get('reason')}")
    else:
        peer_list = peers.get("peers", [])
        tickers = ", ".join(p.get("ticker", "?") for p in peer_list) or "(bos)"
        print(f"Rakipler ({len(peer_list)}): {tickers}")

    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "GECICI TEST ARACI: veri katmanini (pipeline.fetch_stock_data) "
            "calistirir ve bulunan ceyrek sayisi, hangi metriklerin dolu / "
            "'veri yok' oldugu ve her metrik icin eslesen EDGAR XBRL "
            "etiketini ozetleyen bir rapor basar."
        )
    )
    parser.add_argument("ticker", help="Orn: AAPL")
    args = parser.parse_args()

    try:
        data = pipeline.fetch_stock_data(args.ticker)
    except (errors.TickerNotFoundError, errors.SecRequestError) as exc:
        print(f"HATA: {exc}", file=sys.stderr)
        sys.exit(1)

    summary = summarize(data)
    print_report(args.ticker.upper(), data, summary)

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    ticker = args.ticker.upper()

    data_path = os.path.join(config.OUTPUT_DIR, f"{ticker}.json")
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)

    summary_path = os.path.join(config.OUTPUT_DIR, f"{ticker}_verify_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, sort_keys=True)

    print(f"\nYazildi: {data_path}")
    print(f"Yazildi: {summary_path}")


if __name__ == "__main__":
    main()
