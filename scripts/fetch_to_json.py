import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_analysis import config, errors, pipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bir ticker icin veri katmanini calistirip sonucu JSON olarak diske yazar."
    )
    parser.add_argument("ticker", help="Orn: AAPL")
    args = parser.parse_args()

    try:
        data = pipeline.fetch_stock_data(args.ticker)
    except (errors.TickerNotFoundError, errors.SecRequestError) as exc:
        print(f"HATA: {exc}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(config.OUTPUT_DIR, f"{args.ticker.upper()}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(f"Yazildi: {out_path}")


if __name__ == "__main__":
    main()
