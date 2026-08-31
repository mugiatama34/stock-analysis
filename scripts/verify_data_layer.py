import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_analysis import config, errors, pipeline  # noqa: E402

# Ceyrek sozluklerinde ("quarters[qkey]['metrics']") bulunan tum metrikler.
_QUARTER_METRICS = list(config.DURATION_TAG_PRIORITIES) + list(config.INSTANT_TAG_PRIORITIES)


def summarize(data: dict) -> dict:
    """Cekilen veriden, her metrik icin kac ceyrekte deger bulundugunu ve
    hangi EDGAR etiketinin eslestigini cikaran bir ozet uretir."""
    quarters = data["quarters"]

    metrics_summary = {}
    for metric in _QUARTER_METRICS:
        filled = 0
        missing = 0
        tags_used = Counter()
        for quarter in quarters.values():
            entry = quarter["metrics"].get(metric, {})
            if entry.get("value") is None:
                missing += 1
            else:
                filled += 1
                if entry.get("tag"):
                    tags_used[entry["tag"]] += 1
        metrics_summary[metric] = {
            "filled_quarters": filled,
            "missing_quarters": missing,
            "tags_used": dict(tags_used),
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

    header = f"{'Metrik':<28}{'Dolu':>6}{'VeriYok':>9}   Eslesen EDGAR etiket(ler)i"
    print(header)
    print("-" * len(header))
    for metric, info in summary["metrics"].items():
        if info["tags_used"]:
            tags_str = ", ".join(
                f"{tag} ({count} ceyrek)" for tag, count in info["tags_used"].items()
            )
        else:
            tags_str = "(hicbir aday etiket eslesmedi)"
        print(f"{metric:<28}{info['filled_quarters']:>6}{info['missing_quarters']:>9}   {tags_str}")
    print()

    ttm = data.get("ttm", {})
    if ttm.get("available"):
        print("TTM: mevcut")
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
