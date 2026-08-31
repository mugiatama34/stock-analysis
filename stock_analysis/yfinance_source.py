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
    "business_summary": "longBusinessSummary",
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


def fetch_splits(ticker: str) -> list:
    """yfinance'ten hisse bolunme (split) gecmisini ceker. Her oge bir
    bolunme olayi: {"date": "YYYY-MM-DD", "ratio": float} (orn. 4.0 = 4:1
    bolunme, 0.5 = 1:2 ters bolunme). Hata durumunda bos liste doner,
    pipeline'i cokertmez - bu durumda hisse basina degerler normalize
    edilmeden (as-filed) birakilir."""
    try:
        splits = yf.Ticker(ticker).splits
    except Exception:
        return []
    if splits is None or splits.empty:
        return []
    return [
        {"date": idx.strftime("%Y-%m-%d"), "ratio": float(ratio)}
        for idx, ratio in splits.items()
        if ratio
    ]


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
