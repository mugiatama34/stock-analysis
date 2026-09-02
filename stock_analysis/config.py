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

# Ticker SEC'in company_tickers.json listesinde (CIK'i var) olsa bile,
# companyfacts'te 10-Q/10-K kaynakli ceyrek sayisi bunun altindaysa
# errors.InsufficientQuarterlyDataError firlatilir (bkz. pipeline.py).
# Tipik tetikleyici: ADR olarak listelenen yabanci ozel ihraccilar (orn.
# ASML) SEC'e 10-Q/10-K yerine 20-F/6-K dosyalar - CIK bulunur ama
# donemsel us-gaap verisi hic ya da neredeyse hic gelmez. Bu kontrol
# olmadan pipeline sessizce 0 (veya birkac) ceyrekli, tum metrikleri
# "veri yok" bos bir rapor uretiyordu - CLAUDE.md'nin "ABD disi hisse
# desteklenmiyor, net hata mesajiyla dur" kuralini es geciyordu. 8 (2 yil)
# esigi, YoY buyume ve 5 yillik yuzdelik konumlandirma gibi bu aracin
# TASARIM GEREGI ihtiyac duydugu asgari veri miktarina karsilik gelir.
MIN_USABLE_QUARTERS = 8

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
        # Bankalar (orn. JPM) gelirini faiz gideri dusulmus net rakamla
        # raporlar; yukaridaki genel-amacli etiketlerin hicbiri bunlarda
        # bulunmaz.
        "RevenuesNetOfInterestExpense",
        "InterestAndDividendIncomeOperating",
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
#   Opsiyonel "subtract_when_using": {kullanilan_etiket: cikarilacak_etiket}
#   - zincirdeki etiketler ayni kavrami FARKLI KAPSAMDA tanimliyorsa
#   (biri bir alt-kalemi icerir, digeri haric tutar) kullanilir; bkz.
#   long_term_debt asagida.
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
        # LongTermDebt (zincirdeki YEDEK etiket) US-GAAP taksonomisinde
        # CARI KISMI DA icerir; LongTermDebtNoncurrent ise SADECE cari
        # olmayan kismi kapsar. short_term_debt (yukarida) LongTermDebtCurrent'i
        # zaten bir BILESEN olarak topluyor - ayni ceyrekte hem
        # LongTermDebtCurrent hem de (zincir LongTermDebt'e dustugu icin)
        # LongTermDebt raporlanmissa, cari kisim total_debt'te IKI KEZ
        # sayilir (bir short_term_debt'te, bir de long_term_debt'te). F ve
        # GM gibi surekli cari vadeli borcu olan sirketlerde bu her donem
        # tetiklenir (AAPL 2015'te tetiklenmedi cunku o donemde cari vadeli
        # borcu yoktu).
        #
        # Cozum: FLAGLEMEK (ceyregi "veri yok" birakmak) yerine FARKI ALMAK
        # secildi. Gerekce: LongTermDebt ve LongTermDebtCurrent ikisi de
        # ayni ceyrek icin GERCEKTEN RAPORLANMIS iki XBRL kaydidir; aralarindaki
        # farki almak bir TAHMIN ya da interpolasyon degildir (yasak olan
        # "eksik veriyi doldurmak" degil) - kesin bir aritmetik islemdir ve
        # sonuc, LongTermDebtNoncurrent'in zaten temsil ettigi kavramla TAM
        # TUTARLIDIR. Ceyregi flaglemek (veri yok saymak) F ve GM gibi
        # sirketler icin AYLARCA/YILLARCA suren bir bilanco boslugu
        # yaratirdi - cari vadeli borc bu sirketlerde neredeyse her ceyrek
        # mevcuttur, dolayisiyla flag neredeyse her ceyregi vururdu.
        # subtract_when_using, ayni donem sonu icin LongTermDebtCurrent veri
        # donduruyorsa bu farki otomatik uygular (bkz.
        # edgar._resolve_instant_chain).
        "subtract_when_using": {
            "LongTermDebt": "LongTermDebtCurrent",
        },
    },
    # total_debt: UCUNCU COZUMLEME MODU, "chain_with_fallback". Once "tags"
    # listesindeki TEK PARCA toplam borc etiketleri (short_term_debt/
    # long_term_debt gibi ayri kalemlere degil, sirketin dogrudan raporladigi
    # TEK bir "toplam borc" kavramina karsilik gelir) HER CEYREK icin
    # BAGIMSIZ denenir - "chain" moduyla ayni kural (bkz. yukarida). Hicbiri
    # o ceyrek icin veri dondurmuyorsa, "fallback_metrics" listesindeki
    # metriklerin (short_term_debt + long_term_debt) O CEYREK icin ZATEN
    # COZULMUS degerleri toplanir (bkz. edgar._resolve_instant_chain_with_fallback);
    # INSTANT_METRICS sozlugunde bu metriklerden SONRA tanimlanmis olmasi
    # gerekir (build_quarters metrikleri sozluk sirasina gore cozer).
    #
    # DebtAndCapitalLeaseObligations KIRALAMA YUKUMLULUKLERINI de icerir -
    # bu, short_term_debt + long_term_debt toplaminin (sadece finansal
    # borclanmayi kapsar, kira yukumlulugu haric) kapsamindan FARKLIDIR.
    # Iki taban arasinda CIKARMA/DUZELTME YAPILMAZ (subtract_when_using
    # burada yok) - farkli kapsamlari birbirine gecici olarak esitlemek bir
    # tahmin islemi olurdu. Bunun yerine hangi tabanin kullanildigi "tag"
    # alaninda (dogrudan etiket adi ya da fallback icin
    # "short_term_debt+long_term_debt") isaretlenir ve
    # scripts/verify_data_layer.py ceyrek bazinda raporlar - boylece rapor
    # katmani (ileride) gerekirse iki tabani ayri gosterebilir.
    "total_debt": {
        "mode": "chain_with_fallback",
        "tags": [
            "DebtAndCapitalLeaseObligations",
            "DebtLongtermAndShorttermCombinedAmount",
        ],
        "fallback_metrics": ["short_term_debt", "long_term_debt"],
    },
}

# Bilanco (INSTANT_METRICS) serilerinde ETIKET DEGISTIGI ceyrekte, degerin
# bir onceki DOLU ceyrege gore GORELI SICRAMASI bu esigi asarsa dogrulama
# ozetine uyari eklenir (bkz. scripts/verify_data_layer.py
# _continuity_warnings). Amac: "chain" zincirindeki iki etiketin ayni
# kavrami FARKLI KAPSAMDA tanimladigi durumlari otomatik yakalamak - orn.
# long_term_debt'te LongTermDebt cari kismi icerirken LongTermDebtNoncurrent
# haric tutar (bkz. yukarida subtract_when_using). Bu tur bir tanim
# karisikligi ilk kez F/GM gibi surekli cari vadeli borcu olan sirketlerde
# ELLE dogrulama sirasinda bulundu; bu kontrol olsaydi otomatik yakalanirdi.
# %35 esigi, normal ceyrekten ceyrege dalgalanmanin (yeniden finansman,
# mevsimsel nakit ihtiyaci) USTUNDE ama kucuk/onemsiz bir tanim farkinin
# (cari kismin toplam borcun kucuk bir yuzdesi oldugu sirketler) ALTINDA
# kalacak sekilde secilmis bir sezgiseldir; yanlis pozitif/negatif dengesi
# gercek veri uzerinde gozlemlenerek ayarlanabilir.
INSTANT_METRIC_CONTINUITY_THRESHOLD = 0.35

# Sektor istisnasi tespiti icin yfinance sector/industry metninde aranan
# anahtar kelimeler (kucuk harfe cevrilmis metin uzerinde).
FINANCIAL_SECTOR_KEYWORDS = [
    "bank",
    "insurance",
    "reit",
    "real estate investment trust",
]

# "Finansman kolu olan sanayi sirketi" tespiti (CLAUDE.md > Metrikler >
# SEKTOR ISTISNASI ucuncu kategori) icin sirket kunyesinde (yfinance
# longBusinessSummary, kucuk harfe cevrilmis) aranan ifadeler - bkz.
# metrics.classify_financing_arm docstring'i (neden oran degil metin
# tabanli tespit secildigi icin gerekce orada).
FINANCING_ARM_KEYWORDS = [
    "financial services segment",
    "financing segment",
    "captive finance",
    "credit and financing",
    "financing operations",
    "wholesale and retail financing",
    "dealer financing",
    "vehicle financing",
    "equipment financing",
]

# Ikinci (yapisal) finansman kolu sinyali: kunye metni yfinance'in serbest
# Ingilizce ozetine bagimli oldugu icin kirilgan (ozet degisirse veya
# ifadeyi kullanmazsa sessizce calismayi birakir). Bu XBRL etiketleri
# sirketin KENDI SEC dosyalamasindan gelen yapisal bir veridir - bir
# finansman/kredi kolu tipik olarak musteri/bayi alacaklarini bu
# kalemlerden biriyle raporlar. Ikisinden (metin veya etiket) HERHANGI
# BIRI yeterlidir (bkz. metrics.classify_financing_arm).
FINANCING_ARM_XBRL_TAGS = [
    "FinanceReceivablesNetNoncurrent",
    "FinanceReceivablesNetCurrent",
    "FinanceReceivablesNet",
    "NotesReceivableNet",
]

# Render katmani (CLAUDE.md > Rapor katmani > KAPSAM KURALI): bir metrik,
# bulunan ceyreklerin bu oranindan azinda doluysa render'da gizlenir.
RENDER_COVERAGE_THRESHOLD = 0.30

# "Veri yok" ile "sirket bunu artik ayri raporlamiyor" ayrimi (genel kural,
# tek bir sektor/kategoriye ozel degil - bkz. metrics.quarter_reporting_status).
# Bir metrigin dolu oldugu SON ceyrek, verinin kapsadigi SON ceyrekten en az
# bu kadar ceyrek geride ise "kesildi" sayilir. Ford total_debt/net_debt bunun
# somut ornegi: DebtAndCapitalLeaseObligations son kez 2020-Q4 icin
# raporlanmis, veri 2026-Q1'e kadar gidiyor (22+ ceyrek boşluk). 4 (1 yil),
# tek bir ceyreklik rastlantisal bir bosluğu (gecikmis filing, veri kaynagi
# gecikmesi) "kesildi" diye yanlis etiketlememek icin secilen bir esiktir -
# ayni RENDER_COVERAGE_THRESHOLD gibi gercek veri uzerinde gozlemlenerek
# ayarlanabilir.
REPORTING_GAP_QUARTERS_THRESHOLD = 4

# Degerleme yuzdelik konumu (CLAUDE.md > Metrikler > Degerleme) icin
# kullanilan gecmis ceyrek penceresi: en fazla 20 (5 yil), yuzdelik
# hesaplamak icin asgari 12 ceyrek gerekir - daha azsa sadece ham oran
# gosterilir (bkz. metrics.compute_valuation_context).
VALUATION_HISTORY_MAX_QUARTERS = 20
VALUATION_HISTORY_MIN_QUARTERS = 12

REPORTS_DIR = "reports"
