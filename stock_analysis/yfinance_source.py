import yfinance as yf

# result anahtari -> yfinance .info sozluk alani
_INFO_FIELDS = {
    "company_name": "longName",
    "sector": "sector",
    "industry": "industry",
    "employees": "fullTimeEmployees",
    "market_cap": "marketCap",
    "current_price": "currentPrice",
    "shares_outstanding": "sharesOutstanding",
}


def fetch_company_info(ticker: str) -> dict:
    """yfinance info sozlugundeki her alani tek tek okur; eksik/None olan
    alan sonucta None olarak kalir, raporu/pipeline'i cokertmez."""
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        info = {}

    result = {key: info.get(field) for key, field in _INFO_FIELDS.items()}
    if result.get("current_price") is None:
        result["current_price"] = info.get("regularMarketPrice")
    return result


def fetch_price_history(ticker: str, period: str = "5y") -> list:
    try:
        hist = yf.Ticker(ticker).history(period=period)
    except Exception:
        return []
    if hist is None or hist.empty:
        return []

    records = []
    for idx, row in hist.iterrows():
        close = row.get("Close")
        if close is None:
            continue
        records.append({"date": idx.strftime("%Y-%m-%d"), "close": float(close)})
    return records
