from . import config


def _safe_div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def classify_sector(sector, industry) -> dict:
    haystack = f"{sector or ''} {industry or ''}".lower()
    for keyword in config.FINANCIAL_SECTOR_KEYWORDS:
        if keyword in haystack:
            return {
                "is_financial_sector": True,
                "reason": (
                    f"Sektor/endustri bilgisinde '{keyword}' tespit edildi; "
                    "borc ve nakit temelli oranlar bu sektorde anlamsiz."
                ),
            }
    return {"is_financial_sector": False, "reason": None}


def compute_quarter_derived(quarter_metrics: dict) -> dict:
    """Tek bir ceyregin ham EDGAR metriklerinden marj/nakit/bilanco
    turevlerini hesaplar. Herhangi bir girdi None ise sonuc da None kalir,
    tahmin/varsayim yapilmaz."""
    revenue = quarter_metrics["revenue"]["value"]
    cost_of_revenue = quarter_metrics["cost_of_revenue"]["value"]
    gross_profit = None
    if revenue is not None and cost_of_revenue is not None:
        gross_profit = revenue - cost_of_revenue

    operating_income = quarter_metrics["operating_income"]["value"]
    net_income = quarter_metrics["net_income"]["value"]
    ocf = quarter_metrics["operating_cash_flow"]["value"]
    capex = quarter_metrics["capex"]["value"]
    d_and_a = quarter_metrics["depreciation_amortization"]["value"]
    interest_expense = quarter_metrics["interest_expense"]["value"]
    cash = quarter_metrics["cash_and_equivalents"]["value"]
    total_debt = quarter_metrics["total_debt"]["value"]

    fcf = None
    if ocf is not None and capex is not None:
        # XBRL "Payments" kavramlari genelde pozitif nakit cikisi olarak
        # raporlanir, ama bazi filer'lar isareti tersine kullanabiliyor;
        # abs() bu tutarsizliga karsi savunmaci.
        fcf = ocf - abs(capex)

    net_debt = None
    if total_debt is not None and cash is not None:
        net_debt = total_debt - cash

    ebitda = None
    if operating_income is not None and d_and_a is not None:
        ebitda = operating_income + d_and_a

    return {
        "gross_margin": _safe_div(gross_profit, revenue),
        "operating_margin": _safe_div(operating_income, revenue),
        "net_margin": _safe_div(net_income, revenue),
        "fcf": fcf,
        "fcf_vs_net_income": (fcf - net_income) if (fcf is not None and net_income is not None) else None,
        "total_debt": total_debt,
        "net_debt": net_debt,
        "ebitda": ebitda,
        "net_debt_to_ebitda": _safe_div(net_debt, ebitda),
        "interest_coverage": _safe_div(operating_income, interest_expense),
    }


def latest_quarter(quarters: dict):
    items = [(k, v) for k, v in quarters.items() if v.get("period_end")]
    if not items:
        return None
    items.sort(key=lambda kv: kv[1]["period_end"])
    return items[-1][1]


def _last_n_quarters(quarters: dict, n: int = 4):
    items = [(k, v) for k, v in quarters.items() if v.get("period_end")]
    items.sort(key=lambda kv: kv[1]["period_end"])
    return items[-n:]


def compute_ttm(quarters: dict) -> dict:
    """Son 4 ceyrekten trailing-twelve-month toplami. Tam 4 ceyrek yoksa
    veya herhangi bir ceyrekte ilgili metrik eksikse TTM 'veri yok' olarak
    isaretlenir -- kismi toplam uretilmez."""
    last4 = _last_n_quarters(quarters, 4)
    if len(last4) < 4:
        return {"available": False, "reason": "son 4 ceyrek tamamlanmadi"}

    def ttm_sum(metric):
        values = [q["metrics"][metric]["value"] for _, q in last4]
        if any(v is None for v in values):
            return None
        return sum(values)

    revenue_ttm = ttm_sum("revenue")
    net_income_ttm = ttm_sum("net_income")
    eps_ttm = ttm_sum("eps_diluted")
    ocf_ttm = ttm_sum("operating_cash_flow")
    capex_ttm = ttm_sum("capex")
    d_and_a_ttm = ttm_sum("depreciation_amortization")
    operating_income_ttm = ttm_sum("operating_income")

    fcf_ttm = None
    if ocf_ttm is not None and capex_ttm is not None:
        fcf_ttm = ocf_ttm - abs(capex_ttm)

    ebitda_ttm = None
    if operating_income_ttm is not None and d_and_a_ttm is not None:
        ebitda_ttm = operating_income_ttm + d_and_a_ttm

    return {
        "available": True,
        "period_end": last4[-1][1]["period_end"],
        "revenue": revenue_ttm,
        "net_income": net_income_ttm,
        "eps_diluted": eps_ttm,
        "fcf": fcf_ttm,
        "ebitda": ebitda_ttm,
    }


def compute_valuation_ratios(ttm: dict, market_cap, price, cash, total_debt) -> dict:
    if not ttm.get("available"):
        return {"available": False, "reason": ttm.get("reason", "TTM verisi yok")}

    ev = None
    if market_cap is not None and total_debt is not None and cash is not None:
        ev = market_cap + total_debt - cash

    return {
        "available": True,
        "pe": _safe_div(price, ttm["eps_diluted"]),
        "ps": _safe_div(market_cap, ttm["revenue"]),
        "ev_ebitda": _safe_div(ev, ttm["ebitda"]),
        "p_fcf": _safe_div(market_cap, ttm["fcf"]),
    }
