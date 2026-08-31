from . import config


def _safe_div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


_SECTOR_KEYWORD_LABELS = {
    "bank": "Bankalarda",
    "insurance": "Sigorta şirketlerinde",
    "reit": "GYO'larda",
    "real estate investment trust": "GYO'larda",
}


def classify_sector(sector, industry) -> dict:
    haystack = f"{sector or ''} {industry or ''}".lower()
    for keyword in config.FINANCIAL_SECTOR_KEYWORDS:
        if keyword in haystack:
            label = _SECTOR_KEYWORD_LABELS.get(keyword, "Bu sektörde")
            return {
                "is_financial_sector": True,
                "reason": f"{label} borç ve marj temelli bazı oranlar anlamlı değil, bu yüzden gizlendi.",
            }
    return {"is_financial_sector": False, "reason": None}


def classify_financing_arm(business_summary) -> dict:
    """Ford/GM/Caterpillar gibi finansman kolu (captive finance) olan sanayi
    sirketlerini tespit eder - bunlarda kredi/finansman faaliyeti yatirim
    nakit akisinda gorundugu icin klasik FCF ve borc oranlari yaniltici olur
    (bkz. CLAUDE.md > Metrikler > SEKTOR ISTISNASI, ucuncu kategori).

    Tespit YONTEMI olarak sirket kunyesindeki (yfinance longBusinessSummary)
    ACIK finansman-segmenti ifadesi secildi, finansal borc/toplam varlik
    ORANI degil. Gerekce: (1) toplam varliklar (Assets XBRL etiketi) su an
    veri katmaninda cekilen bir metrik degil - bunu eklemek yeni bir instant
    metrik ve yeni bir cekim kapsamı gerektirirdi; (2) oran tabanli bir tespit
    "finansman kolu" sayilacak esigi KEYFI belirlemeyi gerektirir - bu oran
    otomotivde, agir makinede ve perakende kredi kartinda cok farkli
    seviyelerde normaldir, gercek veri uzerinde dogrulanmadan secilecek bir
    esik INSTANT_METRIC_CONTINUITY_THRESHOLD gibi sezgisel kalirdi. Kunyedeki
    segment ifadesi ise sirketin KENDI SEC dosyalarindan/yfinance ozetinden
    gelen bir gercek - tahmin degil, ASLA tahmin etme kuraliyla tutarli."""
    haystack = (business_summary or "").lower()
    for keyword in config.FINANCING_ARM_KEYWORDS:
        if keyword in haystack:
            return {
                "has_financing_arm": True,
                "reason": (
                    "Şirketin finansman kolu (kredi/finansman segmenti) "
                    "faaliyetleri nakit akışını ve borç temelli oranları "
                    "bozduğu için P/FCF ve EV/EBITDA gizlendi."
                ),
            }
    return {"has_financing_arm": False, "reason": None}


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


_LOSS_UNAVAILABLE_LABEL = "hesaplanamaz (zarar)"


def compute_valuation_ratios(ttm: dict, market_cap, price, cash, total_debt) -> dict:
    """TTM net kar <=0 ise F/K, TTM FCF <=0 ise P/FCF hesaplanmaz - negatif
    bir F/K sayisal olarak kucuk gorunup yuzdelik baglaminda yanlislikla
    "tarihi ucuzluk" gibi okunabiliyor, oysa tam tersi (zarar) anlamina
    gelir. Bu durumda oran None birakilir ve "unavailable_reasons" altinda
    render katmaninin "hesaplanamaz (zarar)" gostermesi icin bir sebep
    isaretlenir - render "veri yok" ile bu ikisini KARISTIRMAMALI."""
    if not ttm.get("available"):
        return {"available": False, "reason": ttm.get("reason", "TTM verisi yok")}

    ev = None
    if market_cap is not None and total_debt is not None and cash is not None:
        ev = market_cap + total_debt - cash

    net_income = ttm["net_income"]
    pe = None
    pe_unavailable_reason = None
    if net_income is not None and net_income <= 0:
        pe_unavailable_reason = _LOSS_UNAVAILABLE_LABEL
    else:
        pe = _safe_div(price, ttm["eps_diluted"])

    fcf = ttm["fcf"]
    p_fcf = None
    p_fcf_unavailable_reason = None
    if fcf is not None and fcf <= 0:
        p_fcf_unavailable_reason = _LOSS_UNAVAILABLE_LABEL
    else:
        p_fcf = _safe_div(market_cap, fcf)

    return {
        "available": True,
        "pe": pe,
        "ps": _safe_div(market_cap, ttm["revenue"]),
        "ev_ebitda": _safe_div(ev, ttm["ebitda"]),
        "p_fcf": p_fcf,
        "unavailable_reasons": {
            "pe": pe_unavailable_reason,
            "p_fcf": p_fcf_unavailable_reason,
        },
    }


def _sorted_quarters(quarters: dict) -> list:
    items = [(k, v) for k, v in quarters.items() if v.get("period_end")]
    items.sort(key=lambda kv: kv[1]["period_end"])
    return [v for _, v in items]


def _trailing_flow_sum(ordered_quarters: list, end_idx: int, metric: str):
    """ordered_quarters[end_idx-3..end_idx] (4 ceyrek) icin metric'in
    toplamini dondurur; pencere tam degilse veya herhangi bir ceyrekte
    deger eksikse None (tahmin/kismi toplam yapilmaz)."""
    if end_idx < 3:
        return None
    values = [ordered_quarters[i]["metrics"][metric]["value"] for i in range(end_idx - 3, end_idx + 1)]
    if any(v is None for v in values):
        return None
    return sum(values)


def _price_on_or_before(price_history: list, iso_date: str):
    """price_history tarihe gore artan sirali kabul edilir (yfinance_source.
    fetch_price_history ciktisi). Verilen tarihte veya ondan once islem
    goren en son kapanisi dondurur; hicbiri yoksa None."""
    best = None
    for point in price_history:
        if point["date"] > iso_date:
            break
        best = point["close"]
    return best


def compute_valuation_history(quarters: dict, price_history: list) -> dict:
    """Her ceyrek sonu icin, o tarihteki fiyat ve trailing-TTM degerlerinden
    F/K, P/S, EV/EBITDA, P/FCF oran serisi uretir (CLAUDE.md > Metrikler >
    Degerleme: hissenin kendi 5 yillik araligindaki yuzdelik konumu icin
    girdi). Piyasa degeri, o ceyregin kendi agirlikli ortalama seyreltilmis
    hisse adedi (diluted_shares) ile fiyatin carpimidir - "o tarihteki fiili
    hisse adedi" degil, ama EDGAR'dan zaten cozulmus/tahmin icermeyen tek
    veridir. Herhangi bir girdi eksikse o ceyrek icin o metrik atlanir,
    interpolasyon yapilmaz. Donen serilerin her biri en fazla
    config.VALUATION_HISTORY_MAX_QUARTERS eleman tutar (en yeniden geriye)."""
    ordered = _sorted_quarters(quarters)
    history = {"pe": [], "ps": [], "ev_ebitda": [], "p_fcf": []}

    for i, q in enumerate(ordered):
        price = _price_on_or_before(price_history, q["period_end"])
        if price is None:
            continue

        eps_ttm = _trailing_flow_sum(ordered, i, "eps_diluted")
        net_income_ttm = _trailing_flow_sum(ordered, i, "net_income")
        if net_income_ttm is not None and net_income_ttm <= 0:
            # Zarar ceyregi: F/K o ceyrek icin hic hesaplanmaz, yuzdelik
            # havuzuna da girmez (bkz. compute_valuation_ratios docstring'i -
            # ayni kural gecmis seri icin de gecerli).
            history["pe"].append(None)
        else:
            history["pe"].append(_safe_div(price, eps_ttm))

        shares = q["metrics"]["diluted_shares"]["value"]
        market_cap = price * shares if shares is not None else None

        revenue_ttm = _trailing_flow_sum(ordered, i, "revenue")
        history["ps"].append(_safe_div(market_cap, revenue_ttm))

        ocf_ttm = _trailing_flow_sum(ordered, i, "operating_cash_flow")
        capex_ttm = _trailing_flow_sum(ordered, i, "capex")
        fcf_ttm = (
            ocf_ttm - abs(capex_ttm) if ocf_ttm is not None and capex_ttm is not None else None
        )
        if fcf_ttm is not None and fcf_ttm <= 0:
            history["p_fcf"].append(None)
        else:
            history["p_fcf"].append(_safe_div(market_cap, fcf_ttm))

        operating_income_ttm = _trailing_flow_sum(ordered, i, "operating_income")
        d_and_a_ttm = _trailing_flow_sum(ordered, i, "depreciation_amortization")
        ebitda_ttm = (
            operating_income_ttm + d_and_a_ttm
            if operating_income_ttm is not None and d_and_a_ttm is not None
            else None
        )
        total_debt = q["metrics"]["total_debt"]["value"]
        cash = q["metrics"]["cash_and_equivalents"]["value"]
        ev = (
            market_cap + total_debt - cash
            if market_cap is not None and total_debt is not None and cash is not None
            else None
        )
        history["ev_ebitda"].append(_safe_div(ev, ebitda_ttm))

    for key, values in history.items():
        history[key] = [v for v in values if v is not None][-config.VALUATION_HISTORY_MAX_QUARTERS :]
    return history


def compute_valuation_context(valuation_history: dict, valuation: dict) -> dict:
    """Bugunku (canli) degerleme oraninin, kendi gecmis dagilimindaki
    yuzdelik konumunu hesaplar. Esik (kullanicidan): >=20 ceyrek varsa
    (compute_valuation_history zaten son 20'ye kirpar) tam pencere kullanilir,
    12-19 arasi varsa mevcut sayiyla hesaplanip kac ceyrege dayandigi ayrica
    dondurulur, 12'nin altinda yuzdelik HIC hesaplanmaz (sadece ham oran
    gosterilir - bkz. render.py)."""
    if not valuation.get("available"):
        return {}

    context = {}
    for key in ("pe", "ps", "ev_ebitda", "p_fcf"):
        current = valuation.get(key)
        series = valuation_history.get(key, [])
        n = len(series)
        if current is None or n == 0:
            context[key] = {"status": "no_data", "quarters_used": n}
        elif n < config.VALUATION_HISTORY_MIN_QUARTERS:
            context[key] = {"status": "insufficient_history", "quarters_used": n}
        else:
            percentile = sum(1 for v in series if v <= current) / n * 100
            context[key] = {"status": "ok", "quarters_used": n, "percentile": percentile}
    return context
