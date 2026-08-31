import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_analysis import config, render  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="output/TICKER.json'dan reports/TICKER.html uretir."
    )
    parser.add_argument("ticker", help="Orn: AAPL")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    in_path = os.path.join(config.OUTPUT_DIR, f"{ticker}.json")
    if not os.path.exists(in_path):
        print(f"HATA: {in_path} bulunamadi. Once scripts/fetch_to_json.py calistirilmali.", file=sys.stderr)
        sys.exit(1)

    with open(in_path, encoding="utf-8") as f:
        data = json.load(f)

    html = render.render_report(data, generated_at=date.today().isoformat())

    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    out_path = os.path.join(config.REPORTS_DIR, f"{ticker}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Yazildi: {out_path}")


if __name__ == "__main__":
    main()
