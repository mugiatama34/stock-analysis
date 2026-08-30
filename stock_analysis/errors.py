class StockAnalysisError(Exception):
    """Tum modul-ozel hatalarin temel sinifi."""


class TickerNotFoundError(StockAnalysisError):
    """Ticker SEC EDGAR company_tickers.json listesinde bulunamadi."""


class SecRequestError(StockAnalysisError):
    """SEC EDGAR'a yapilan bir istek basarisiz oldu."""
