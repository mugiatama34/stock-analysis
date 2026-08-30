import requests

from . import config

# Finnhub /stock/metric?metric=all alan adlari. Finnhub dokumantasyonuna
# gore zaman zaman degisebilir; her alan .get() ile okunur, eksikse None
# doner (rapor "veri yok" gosterir), pipeline cokmez.
_SNAPSHOT_FIELDS = {
    "pe_ttm": "peTTM",
    "ps_ttm": "psTTM",
    "pb_annual": "pbAnnual",
    "gross_margin_ttm": "grossMarginTTM",
    "operating_margin_ttm": "operatingMarginTTM",
    "net_margin_ttm": "netProfitMarginTTM",
    "revenue_growth_yoy_quarterly": "revenueGrowthQuarterlyYoy",
    "eps_growth_yoy_quarterly": "epsGrowthQuarterlyYoy",
}


def fetch_peers(ticker: str) -> dict:
    """Ilk 5 rakip icin anlik degerleme/marj kesiti. Herhangi bir Finnhub
    istegi hata donerse rakip bolumu 'unavailable' olarak isaretlenir,
    exception yukari firlatilmaz -- raporun geri kalani normal uretilir."""
    if not config.FINNHUB_API_KEY:
        return {"status": "unavailable", "peers": [], "reason": "FINNHUB_API_KEY tanimli degil"}

    try:
        resp = requests.get(
            config.FINNHUB_PEERS_URL,
            params={"symbol": ticker.upper(), "token": config.FINNHUB_API_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        raw_peers = resp.json()
    except requests.RequestException as exc:
        return {"status": "unavailable", "peers": [], "reason": str(exc)}

    if not isinstance(raw_peers, list):
        return {"status": "unavailable", "peers": [], "reason": "beklenmeyen yanit bicimi"}

    candidates = [p for p in raw_peers if isinstance(p, str) and p.upper() != ticker.upper()]
    candidates = candidates[: config.MAX_PEERS]

    snapshots = []
    for peer_ticker in candidates:
        snapshot = _fetch_peer_snapshot(peer_ticker)
        snapshot["ticker"] = peer_ticker
        snapshots.append(snapshot)

    return {"status": "ok", "peers": snapshots}


def _fetch_peer_snapshot(peer_ticker: str) -> dict:
    try:
        resp = requests.get(
            config.FINNHUB_METRIC_URL,
            params={"symbol": peer_ticker, "metric": "all", "token": config.FINNHUB_API_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        metric = resp.json().get("metric", {}) or {}
    except requests.RequestException as exc:
        return {"status": "unavailable", "reason": str(exc)}

    result = {"status": "ok"}
    result.update({key: metric.get(field) for key, field in _SNAPSHOT_FIELDS.items()})
    return result
