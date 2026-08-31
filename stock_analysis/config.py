import os

SEC_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

FINNHUB_PEERS_URL = "https://finnhub.io/api/v1/stock/peers"
FINNHUB_METRIC_URL = "https://finnhub.io/api/v1/stock/metric"

SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", "")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")

CACHE_DIR = "cache"
OUTPUT_DIR = "output"

MAX_PEERS = 5

# Seri 2010 mali yilindan itibaren baslar. Daha erken ceyrekler (orn. AAPL
# icin tek basina duran 2009-Q1 - 2009'un diger uc ceyregi companyfacts'te
# yok) yaniltici tek-nokta gorunumler birakiyor; build_quarters bu yildan
# once kalan (fy, fp) anahtarlarini uretmez.
MIN_FISCAL_YEAR = 2010

# Her metrik icin sirali XBRL us-gaap tag adaylari. Bunlar "duration" (donem
# boyunca akan) kalemlerdir: gelir tablosu ve nakit akis kalemleri.
# Sirketler zaman icinde etiket degistirebilir (orn. ASC 606 sonrasi gelir
# etiketi, ya da birkac yil sureyle "ContinuingOperations" varyanti). Bu
# yuzden ceyreklik cozumleme (edgar.build_quarters) TEK etiketle durmaz,
# listedeki TUM etiketlerin verisini birlestirir; ayni donem icin birden
# fazla etiket varsa listede once gelen kazanir. Sira, ayni kavramin farkli
# etiketleri arasinda tercih sirasidir.
DURATION_TAG_PRIORITIES = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
    ],
    "cost_of_revenue": [
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
        "CostOfServices",
    ],
    "operating_income": [
        "OperatingIncomeLoss",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ],
    "diluted_shares": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingDiluted",
    ],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsForCapitalImprovements",
    ],
    "depreciation_amortization": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAndAmortization",
    ],
    "interest_expense": [
        "InterestExpense",
        "InterestExpenseDebt",
        "InterestExpenseNonoperating",
    ],
}
# gross_profit ve eps_diluted BILEREK burada yok: XBRL etiketinden degil,
# gelir-satis maliyeti / net kar-seyreltilmis hisse adedinden hesaplanir
# (bkz. edgar.build_quarters). Boylece filer'in "brut kar" tanimindaki
# tutarsizliga bagli kalinmaz.

# DURATION_TAG_PRIORITIES'teki her metrik ya AKIS (donem boyunca biriken,
# cikarma ile Q4 = yillik - Q1 - Q2 - Q3 turetilebilen) ya da ORTALAMA
# (agirlikli ortalama bir stok degeri, cikarma islemi ANLAMSIZ) olarak
# siniflandirilmalidir. diluted_shares agirlikli ortalama hisse adedidir -
# yillik ortalamadan ilk uc ceyregin ortalamasi cikarilamaz (negatif/hatali
# sonuc verir, bkz. edgar.resolve_duration_quarters). Yeni bir metrik
# DURATION_TAG_PRIORITIES'e eklendiginde bu iki kumeden birine ELLE
# eklenmesi zorunludur; build_quarters bunu dogrular (bkz. assert).
FLOW_METRICS = {
    "revenue",
    "cost_of_revenue",
    "operating_income",
    "net_income",
    "operating_cash_flow",
    "capex",
    "depreciation_amortization",
    "interest_expense",
}
AVERAGE_METRICS = {
    "diluted_shares",
}

# "instant" (bir tarihteki anlik) kalemler: bilanco kalemleri. Ceyrek sonu
# tarihine gore dogrudan okunur, turetme yapilmaz. Listedeki etiketler ayni
# kavramin FARKLI TANIMLARI olabilir (orn. LongTermDebt ile
# LongTermDebtNoncurrent ayni sey degildir) - bu yuzden duration
# metriklerinin aksine BIRLESTIRILMEZ: sirket genelinde veri donduren ILK
# etiket sabit olarak kullanilir, ceyrekten ceyrege farkli tanima gecilmez.
INSTANT_TAG_PRIORITIES = {
    "cash_and_equivalents": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "short_term_debt": [
        "ShortTermBorrowings",
        "DebtCurrent",
        "LongTermDebtCurrent",
    ],
    "long_term_debt": [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
    ],
}

# Bazi bilanco kalemleri ana etiketin ALTERNATIFI degil, TAMAMLAYICISIDIR:
# sirket ikisine de ayni anda sahip olabilir (orn. kisa vadeli borclanma +
# ticari senet). Bu yuzden fallback zincirine degil, ayrica toplanan bir
# bilesen listesine konur. Eksikse 0 sayilir (yoklugu "veri yok" degil,
# o bilesenin sirkette bulunmadigi anlamina gelir).
INSTANT_ADDITIVE_TAGS = {
    "short_term_debt": [
        "CommercialPaper",
    ],
}

# Sektor istisnasi tespiti icin yfinance sector/industry metninde aranan
# anahtar kelimeler (kucuk harfe cevrilmis metin uzerinde).
FINANCIAL_SECTOR_KEYWORDS = [
    "bank",
    "insurance",
    "reit",
    "real estate investment trust",
]
