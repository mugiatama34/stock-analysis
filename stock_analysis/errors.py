class StockAnalysisError(Exception):
    """Tum modul-ozel hatalarin temel sinifi."""


class TickerNotFoundError(StockAnalysisError):
    """Ticker SEC EDGAR company_tickers.json listesinde bulunamadi."""


class SecRequestError(StockAnalysisError):
    """SEC EDGAR'a yapilan bir istek basarisiz oldu."""


class InsufficientQuarterlyDataError(StockAnalysisError):
    """Ticker'in CIK'i bulundu ama companyfacts'te 10-Q/10-K kaynakli
    kullanilabilir ceyrek sayisi config.MIN_USABLE_QUARTERS'in altinda.
    Tipik neden: sirket SEC'e 10-Q/10-K yerine 20-F/6-K dosyaliyor (yabanci
    ozel ihracci, orn. ASML) - us-gaap taksonomisiyle donemsel veri hic
    veya neredeyse hic gelmiyor (bkz. edgar.resolve_duration_quarters /
    resolve_instant_values, sadece 10-Q/10-K formlarini isliyor)."""
