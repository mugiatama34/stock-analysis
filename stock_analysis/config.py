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
# tarihine gore dogrudan okunur, turetme yapilmaz. Her metrik iki
# COZUMLEME MODUNDAN biriyle tanimlanir (bkz. edgar._resolve_instant_metric):
#
# - "chain" (oncelik zinciri): listedeki etiketler ayni kavramin ALTERNATIF
#   tanimlaridir (orn. sirket bir ceyrekte gecici olarak LongTermDebtNoncurrent
#   yerine LongTermDebt kullanmis olabilir - bu genelde XBRL hazirlayici
#   tutarsizligidir, gercek tanim degisikligi degil). HER CEYREK BAGIMSIZ
#   cozulur: o ceyrek icin veri donduren ILK etiket kullanilir. Sirket
#   genelinde tek etikete kilitlenilmez - aksi halde bir ceyrekte gecici
#   etiket degisimi, veri ASLINDA VARKEN o ceyregi "veri yok" birakir.
#
# - "sum" (bilesen toplami): sirketin AYNI ANDA sahip olabilecegi FARKLI
#   kalemlerin toplamidir (orn. kisa vadeli borclanma + ticari senet).
#   "primary" (varsa) TEK BASINA zaten toplam sayilan bir kalemdir (orn.
#   DebtCurrent) - o ceyrek icin veri donduruyorsa TEK BASINA kullanilir,
#   "components" listesine HIC bakilmaz (ikisini toplamak cift sayima yol
#   acar). primary o ceyrek icin veri dondurmuyorsa, components'taki
#   bulunan TUM etiketlerin degeri toplanir; bulunamayan bilesen 0 sayilir
#   (yoklugu "veri yok" degil, o bilesenin sirkette bulunmadigi anlamina
#   gelir). Bankalar ve finansman kolu olan sirketler gibi coklu borc
#   kalemi bilesenine sahip sirketler icin gerekli.
INSTANT_METRICS = {
    "cash_and_equivalents": {
        "mode": "chain",
        "tags": [
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ],
    },
    "short_term_debt": {
        "mode": "sum",
        "primary": "DebtCurrent",
        "components": [
            "CommercialPaper",
            "LongTermDebtCurrent",
            "ShortTermBorrowings",
        ],
    },
    "long_term_debt": {
        "mode": "chain",
        "tags": [
            "LongTermDebtNoncurrent",
            "LongTermDebt",
        ],
    },
}

# Sektor istisnasi tespiti icin yfinance sector/industry metninde aranan
# anahtar kelimeler (kucuk harfe cevrilmis metin uzerinde).
FINANCIAL_SECTOR_KEYWORDS = [
    "bank",
    "insurance",
    "reit",
    "real estate investment trust",
]
