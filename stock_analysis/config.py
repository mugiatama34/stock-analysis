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

# Her metrik icin sirali XBRL us-gaap tag adaylari. Ilk dolu olan kullanilir.
# Bunlar "duration" (donem boyunca akan) kalemlerdir: gelir tablosu ve nakit
# akis kalemleri. Ceyreklik turetme (bkz. edgar.resolve_duration_quarters)
# bu kalemlere uygulanir.
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
    "gross_profit": [
        "GrossProfit",
    ],
    "operating_income": [
        "OperatingIncomeLoss",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ],
    "eps_diluted": [
        "EarningsPerShareDiluted",
        "EarningsPerShareBasicAndDiluted",
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

# "instant" (bir tarihteki anlik) kalemler: bilanco kalemleri. Ceyrek sonu
# tarihine gore dogrudan okunur, turetme yapilmaz.
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

# Sektor istisnasi tespiti icin yfinance sector/industry metninde aranan
# anahtar kelimeler (kucuk harfe cevrilmis metin uzerinde).
FINANCIAL_SECTOR_KEYWORDS = [
    "bank",
    "insurance",
    "reit",
    "real estate investment trust",
]
