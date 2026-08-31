"""yfinance'in sector/industry alanlari icin Turkce karsiliklar.

yfinance bu alanlari sabit, kucuk bir listeden (Yahoo Finance taksonomisi)
dondurur - serbest metin degildir. Bu yuzden sozluk esleme yeterlidir.
Esleme, yfinance'in dondurdugu METNE (buyuk/kucuk harf dahil) BIREBIR
uymalidir; anahtar degistirmeden yeni satir eklemek yeterlidir.

Sozlukte olmayan bir deger (yeni bir Yahoo Finance kategorisi ya da
beklenmeyen bir metin) ORIJINAL INGILIZCE haliyle gosterilir - CLAUDE.md
geregi "eslesme yoksa ingilizce orijinali goster", asla tahmini bir
ceviri uydurulmaz.
"""

SECTOR_TR = {
    "Technology": "Teknoloji",
    "Healthcare": "Sağlık",
    "Financial Services": "Finansal Hizmetler",
    "Consumer Cyclical": "İsteğe Bağlı Tüketim",
    "Consumer Defensive": "Zorunlu Tüketim",
    "Industrials": "Sanayi",
    "Communication Services": "İletişim Hizmetleri",
    "Energy": "Enerji",
    "Basic Materials": "Temel Malzemeler",
    "Real Estate": "Gayrimenkul",
    "Utilities": "Kamu Hizmetleri",
}

INDUSTRY_TR = {
    # Technology
    "Consumer Electronics": "Tüketici Elektroniği",
    "Information Technology Services": "Bilgi Teknolojileri Hizmetleri",
    "Software - Application": "Yazılım - Uygulama",
    "Software - Infrastructure": "Yazılım - Altyapı",
    "Semiconductors": "Yarı İletkenler",
    "Semiconductor Equipment & Materials": "Yarı İletken Ekipman ve Malzemeleri",
    "Computer Hardware": "Bilgisayar Donanımı",
    "Communication Equipment": "İletişim Ekipmanları",
    "Electronic Components": "Elektronik Bileşenler",
    "Electronics & Computer Distribution": "Elektronik ve Bilgisayar Dağıtımı",
    "Scientific & Technical Instruments": "Bilimsel ve Teknik Aletler",
    "Solar": "Güneş Enerjisi",
    # Communication Services
    "Internet Content & Information": "İnternet İçerik ve Bilgi Hizmetleri",
    "Telecom Services": "Telekomünikasyon Hizmetleri",
    "Entertainment": "Eğlence",
    "Electronic Gaming & Multimedia": "Elektronik Oyun ve Multimedya",
    "Broadcasting": "Yayıncılık",
    "Advertising Agencies": "Reklam Ajansları",
    "Publishing": "Yayıncılık (Basılı/Dijital)",
    # Healthcare
    "Drug Manufacturers - General": "İlaç Üreticileri - Genel",
    "Drug Manufacturers - Specialty & Generic": "İlaç Üreticileri - Özel ve Jenerik",
    "Biotechnology": "Biyoteknoloji",
    "Medical Devices": "Tıbbi Cihazlar",
    "Medical Instruments & Supplies": "Tıbbi Aletler ve Malzemeler",
    "Diagnostics & Research": "Tanı ve Araştırma",
    "Medical Care Facilities": "Sağlık Tesisleri",
    "Health Information Services": "Sağlık Bilgi Hizmetleri",
    "Healthcare Plans": "Sağlık Sigortası Planları",
    "Pharmaceutical Retailers": "Eczane Zincirleri",
    "Medical Distribution": "Tıbbi Ürün Dağıtımı",
    # Financial Services
    "Banks - Diversified": "Bankalar - Çeşitlendirilmiş",
    "Banks - Regional": "Bankalar - Bölgesel",
    "Banks - Global": "Bankalar - Küresel",
    "Insurance - Life": "Sigorta - Hayat",
    "Insurance - Property & Casualty": "Sigorta - Mülk ve Kaza",
    "Insurance - Diversified": "Sigorta - Çeşitlendirilmiş",
    "Insurance - Reinsurance": "Sigorta - Reasürans",
    "Insurance - Specialty": "Sigorta - İhtisas",
    "Insurance Brokers": "Sigorta Brokerleri",
    "Asset Management": "Varlık Yönetimi",
    "Capital Markets": "Sermaye Piyasaları",
    "Financial Data & Stock Exchanges": "Finansal Veri ve Borsalar",
    "Credit Services": "Kredi Hizmetleri",
    "Mortgage Finance": "Mortgage Finansmanı",
    "Shell Companies": "Kabuk Şirketler",
    # Consumer Cyclical
    "Auto Manufacturers": "Otomobil Üreticileri",
    "Auto Parts": "Otomobil Yedek Parçaları",
    "Auto & Truck Dealerships": "Otomobil ve Kamyon Bayilikleri",
    "Recreational Vehicles": "Rekreasyonel Araçlar",
    "Furnishings, Fixtures & Appliances": "Mobilya, Tesisat ve Beyaz Eşya",
    "Residential Construction": "Konut İnşaatı",
    "Textile Manufacturing": "Tekstil Üretimi",
    "Apparel Manufacturing": "Hazır Giyim Üretimi",
    "Apparel Retail": "Hazır Giyim Perakendesi",
    "Footwear & Accessories": "Ayakkabı ve Aksesuar",
    "Packaging & Containers": "Ambalaj ve Konteyner",
    "Personal Services": "Kişisel Hizmetler",
    "Restaurants": "Restoranlar",
    "Lodging": "Konaklama",
    "Resorts & Casinos": "Tatil Köyleri ve Kumarhaneler",
    "Travel Services": "Seyahat Hizmetleri",
    "Specialty Retail": "İhtisas Perakendeciliği",
    "Luxury Goods": "Lüks Tüketim Ürünleri",
    "Home Improvement Retail": "Ev Geliştirme Perakendesi",
    "Department Stores": "Büyük Mağazalar",
    "Discount Stores": "İndirim Mağazaları",
    "Internet Retail": "İnternet Perakendeciliği",
    "Gambling": "Kumar",
    # Consumer Defensive
    "Grocery Stores": "Market Zincirleri",
    "Household & Personal Products": "Ev ve Kişisel Bakım Ürünleri",
    "Packaged Foods": "Ambalajlı Gıda Ürünleri",
    "Beverages - Non-Alcoholic": "İçecekler - Alkolsüz",
    "Beverages - Wineries & Distilleries": "İçecekler - Şaraphane ve İmalathane",
    "Beverages - Brewers": "İçecekler - Bira Üreticileri",
    "Confectioners": "Şekerleme Üreticileri",
    "Farm Products": "Tarım Ürünleri",
    "Tobacco": "Tütün",
    "Education & Training Services": "Eğitim ve Öğretim Hizmetleri",
    # Industrials
    "Aerospace & Defense": "Havacılık ve Savunma",
    "Airlines": "Havayolları",
    "Airports & Air Services": "Havalimanları ve Hava Hizmetleri",
    "Railroads": "Demiryolları",
    "Trucking": "Karayolu Nakliyeciliği",
    "Marine Shipping": "Deniz Taşımacılığı",
    "Integrated Freight & Logistics": "Entegre Kargo ve Lojistik",
    "Industrial Distribution": "Endüstriyel Dağıtım",
    "Business Equipment & Supplies": "İş Ekipmanları ve Malzemeleri",
    "Specialty Business Services": "İhtisas İş Hizmetleri",
    "Consulting Services": "Danışmanlık Hizmetleri",
    "Staffing & Employment Services": "İnsan Kaynakları ve İstihdam Hizmetleri",
    "Security & Protection Services": "Güvenlik Hizmetleri",
    "Waste Management": "Atık Yönetimi",
    "Pollution & Treatment Controls": "Kirlilik ve Arıtma Kontrolü",
    "Engineering & Construction": "Mühendislik ve İnşaat",
    "Building Products & Equipment": "Yapı Ürünleri ve Ekipmanları",
    "Farm & Heavy Construction Machinery": "Tarım ve Ağır İnşaat Makineleri",
    "Metal Fabrication": "Metal İşleme",
    "Tools & Accessories": "El Aletleri ve Aksesuarlar",
    "Electrical Equipment & Parts": "Elektrikli Ekipman ve Parçalar",
    "Specialty Industrial Machinery": "İhtisas Endüstriyel Makineler",
    "Conglomerates": "Holdingler",
    "Rental & Leasing Services": "Kiralama Hizmetleri",
    # Energy
    "Oil & Gas Integrated": "Petrol ve Gaz - Entegre",
    "Oil & Gas E&P": "Petrol ve Gaz - Arama ve Üretim",
    "Oil & Gas Midstream": "Petrol ve Gaz - Taşıma ve Depolama",
    "Oil & Gas Refining & Marketing": "Petrol ve Gaz - Rafinaj ve Pazarlama",
    "Oil & Gas Equipment & Services": "Petrol ve Gaz - Ekipman ve Hizmetler",
    "Oil & Gas Drilling": "Petrol ve Gaz - Sondaj",
    "Thermal Coal": "Termal Kömür",
    "Uranium": "Uranyum",
    # Basic Materials
    "Agricultural Inputs": "Tarımsal Girdiler",
    "Building Materials": "Yapı Malzemeleri",
    "Chemicals": "Kimyasallar",
    "Specialty Chemicals": "İhtisas Kimyasalları",
    "Lumber & Wood Production": "Kereste ve Ahşap Üretimi",
    "Paper & Paper Products": "Kağıt ve Kağıt Ürünleri",
    "Aluminum": "Alüminyum",
    "Copper": "Bakır",
    "Other Industrial Metals & Mining": "Diğer Endüstriyel Metaller ve Madencilik",
    "Gold": "Altın",
    "Silver": "Gümüş",
    "Other Precious Metals & Mining": "Diğer Değerli Metaller ve Madencilik",
    "Coking Coal": "Kok Kömürü",
    "Steel": "Çelik",
    # Real Estate
    "Real Estate - Development": "Gayrimenkul - Geliştirme",
    "Real Estate Services": "Gayrimenkul Hizmetleri",
    "Real Estate - Diversified": "Gayrimenkul - Çeşitlendirilmiş",
    "REIT - Residential": "GYO - Konut",
    "REIT - Office": "GYO - Ofis",
    "REIT - Retail": "GYO - Perakende",
    "REIT - Industrial": "GYO - Endüstriyel",
    "REIT - Healthcare Facilities": "GYO - Sağlık Tesisleri",
    "REIT - Hotel & Motel": "GYO - Otel ve Motel",
    "REIT - Diversified": "GYO - Çeşitlendirilmiş",
    "REIT - Specialty": "GYO - İhtisas",
    "REIT - Mortgage": "GYO - Mortgage",
    # Utilities
    "Utilities - Regulated Electric": "Kamu Hizmetleri - Düzenlenmiş Elektrik",
    "Utilities - Regulated Gas": "Kamu Hizmetleri - Düzenlenmiş Gaz",
    "Utilities - Regulated Water": "Kamu Hizmetleri - Düzenlenmiş Su",
    "Utilities - Diversified": "Kamu Hizmetleri - Çeşitlendirilmiş",
    "Utilities - Renewable": "Kamu Hizmetleri - Yenilenebilir",
    "Utilities - Independent Power Producers": "Kamu Hizmetleri - Bağımsız Elektrik Üreticileri",
}


def translate_sector(sector):
    if sector is None:
        return None
    return SECTOR_TR.get(sector, sector)


def translate_industry(industry):
    if industry is None:
        return None
    return INDUSTRY_TR.get(industry, industry)
