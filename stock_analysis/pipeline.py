from . import cache, edgar, finnhub_source, metrics, yfinance_source


def fetch_stock_data(ticker: str) -> dict:
    """Tek bir ABD hissesi icin EDGAR + yfinance + Finnhub verisini cekip
    tek bir Python sozlugu olarak dondurur. Ticker SEC listesinde yoksa
    edgar.TickerNotFoundError yukari firlar ve is durur."""
    ticker = ticker.upper()

    cik = edgar.get_cik(ticker)

    cached = cache.load_cache(ticker)
    companyfacts = edgar.fetch_companyfacts(cik)
    new_quarters = edgar.build_quarters(companyfacts, cached_quarters=cached.get("quarters", {}))
    all_quarters = cache.merge_quarters(cached.get("quarters", {}), new_quarters)
    cache.save_cache(ticker, cik, all_quarters)

    for quarter in all_quarters.values():
        quarter["derived_metrics"] = metrics.compute_quarter_derived(quarter["metrics"])

    company_info = yfinance_source.fetch_company_info(ticker)
    price_history = yfinance_source.fetch_price_history(ticker)
    sector_flag = metrics.classify_sector(company_info.get("sector"), company_info.get("industry"))

    ttm = metrics.compute_ttm(all_quarters)
    last_quarter = metrics.latest_quarter(all_quarters)
    total_debt = last_quarter["derived_metrics"]["total_debt"] if last_quarter else None
    cash_value = last_quarter["metrics"]["cash_and_equivalents"]["value"] if last_quarter else None

    valuation = metrics.compute_valuation_ratios(
        ttm,
        market_cap=company_info.get("market_cap"),
        price=company_info.get("current_price"),
        cash=cash_value,
        total_debt=total_debt,
    )

    peers = finnhub_source.fetch_peers(ticker)

    return {
        "ticker": ticker,
        "cik": cik,
        "company_name": company_info.get("company_name"),
        "sector": company_info.get("sector"),
        "industry": company_info.get("industry"),
        "employees": company_info.get("employees"),
        "market_cap": company_info.get("market_cap"),
        "current_price": company_info.get("current_price"),
        "shares_outstanding": company_info.get("shares_outstanding"),
        "sector_flag": sector_flag,
        "quarters": all_quarters,
        "ttm": ttm,
        "valuation": valuation,
        "price_history": price_history,
        "peers": peers,
    }
