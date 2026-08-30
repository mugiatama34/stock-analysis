import json
import os
from datetime import datetime, timezone

from . import config


def cache_path(ticker: str) -> str:
    return os.path.join(config.CACHE_DIR, f"{ticker.upper()}.json")


def load_cache(ticker: str) -> dict:
    path = cache_path(ticker)
    if not os.path.exists(path):
        return {"ticker": ticker.upper(), "cik": None, "last_fetched_at": None, "quarters": {}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def merge_quarters(existing: dict, new: dict) -> dict:
    merged = dict(existing)
    merged.update(new)
    return merged


def save_cache(ticker: str, cik: str, quarters: dict) -> None:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    data = {
        "ticker": ticker.upper(),
        "cik": cik,
        "last_fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "quarters": quarters,
    }
    with open(cache_path(ticker), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
