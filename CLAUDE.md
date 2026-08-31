# stock-analysis

Tek bir ABD hissesi için temel ve bilanço analizi üreten araç.
Çıktı: mugiatama34.github.io/stock-analysis/

## Amaç ve sınır
Veriyi getirir, zaman içindeki değişimi ve rakiplerle kıyası gösterir.
Yorumu kullanıcıya bırakır.

KESİNLİKLE ÜRETİLMEYECEK: puan, skor, "ucuz/pahalı" etiketi, al/sat
sinyali, hedef fiyat, analist tavsiyesi, öneri cümlesi.

## Çalışma modeli
GitHub Actions, workflow_dispatch, tek girdi: ticker.
Çıktı /reports/TICKER.html + kök index.html'e satır eklenmesi.
Actions sonucu repoya commit eder.

## Veri kaynakları

### SEC EDGAR companyfacts — ana hissenin çeyreklik geçmişi
- Ticker→CIK eşlemesi SEC'in company_tickers.json dosyasından.
- Her istekte User-Agent header'ı zorunlu. Değer SEC_USER_AGENT
  secret'ından gelir. Header'sız istek SEC tarafından bloklanır.
- Ticker bu listede yoksa iş net bir hata mesajıyla durur.
  ABD dışı hisse desteklenmiyor; kısıtlı modda çalıştırma.

ETİKET ÖNCELİK ZİNCİRİ: aynı kalem şirketten şirkete farklı XBRL
etiketiyle gelir (gelir için Revenues / RevenueFromContractWith
CustomerExcludingAssessedTax / SalesRevenueNet gibi). Her metrik için
sıralı bir aday etiket listesi tanımla, ilk dolu olanı kullan.
Hiçbiri yoksa o metriği "veri yok" olarak işaretle. ASLA tahmin etme,
interpolasyon yapma, sıfır yazma.

4. ÇEYREK TÜRETME: 10-Q'larda bazı kalemler yıl başından itibaren
kümülatiftir. Q4 doğrudan yoktur; yıllık toplamdan Q1+Q2+Q3 çıkarılarak
hesaplanır. Bu yapılmazsa Q4 sistematik olarak şişik çıkar.

ÖNBELLEK: çekilen EDGAR verisi /cache/TICKER.json olarak repoya yazılır.
Aynı ticker tekrar çalıştırılınca sadece eksik çeyrekler çekilir.

### yfinance — şirket bilgisi ve güncel veriler
Sektör, iş tanımı, çalışan sayısı, piyasa değeri, fiyat geçmişi.
info sözlüğündeki alanlar sık sık None gelir; her alanı tek tek kontrol
et, eksikse "veri yok" göster, raporu çökertme.
info'daki hazır oranlara güvenme. Hesaplanabilen her oranı EDGAR
tablolarından kendin hesapla.

### Finnhub /stock/peers — rakip listesi
Anahtar FINNHUB_API_KEY secret'ından. İlk 5 rakip, ana ticker listeden
ayıklanır. Rakipler için sadece anlık kesit çekilir (değerleme oranları,
marjlar, son çeyrek büyüme) — rakiplerin geçmişi çekilmez.
İstek hata dönerse rakip bölümü "veri alınamadı" der, rapor geri kalanı
normal üretilir. Tüm rapor çökmemeli.

## Metrikler
Büyüme: gelir ve EPS, yıllık bazda çeyrek karşılaştırması (YoY).
  QoQ kullanma, mevsimsellik yanıltır.
Kârlılık: brüt / faaliyet / net marj, zaman serisi olarak.
Nakit: FCF (OCF − CapEx) ve net kâr ile arasındaki fark.
Bilanço: net borç, net borç/EBITDA, faiz karşılama oranı.
Seyreltme: hisse adedi trendi.
Değerleme: F/K, P/S, EV/EBITDA, P/FCF — her biri iki bağlamla:
  (a) hissenin kendi 5 yıllık aralığındaki yüzdelik konumu
  (b) rakip medyanı

TTM net kâr <= 0 ise F/K, TTM FCF <= 0 ise P/FCF HESAPLANMAZ (negatif bir
oran, düşük yüzdelik konumuyla birlikte yanlışlıkla "tarihi ucuzluk" gibi
okunuyor — oysa zarar anlamına gelir). Bu durumda sayı ve yüzdelik yerine
"hesaplanamaz (zarar)" gösterilir. 5 yıllık yüzdelik serisi kurulurken de
net kârın (F/K için) veya FCF'nin (P/FCF için) negatif olduğu çeyrekler
seriden dışlanır.

SEKTÖR İSTİSNASI: üç kategori var.
  1. Banka, sigorta ve GYO'larda borç ve marj temelli oranların çoğu
     anlamsız. Sektör bunlardan biriyse ilgili metrikleri gizle ve
     raporda nedenini tek cümleyle belirt.
  2. Finansman kolu olan sanayi şirketi (örn. Ford/GM/Caterpillar gibi
     captive finance kolu olanlar): kredi/finansman faaliyeti yatırım
     nakit akışında göründüğü için klasik FCF ve borç oranları yanıltıcı
     olur. Tespit, şirket künyesinde (yfinance longBusinessSummary)
     açık bir finansman/kredi segmenti ifadesi geçmesine dayanır — bir
     oran eşiği (finansal borç/toplam varlık gibi) DEĞİL, çünkü (a)
     toplam varlıklar veri katmanında henüz çekilen bir metrik değil,
     (b) sektöre göre çok değişen böyle bir eşik gerçek veriyle
     doğrulanmadan keyfi kalır. Bu kategoride sadece P/FCF ve EV/EBITDA
     gizlenir — şirketin kendi marj/borç oranları hâlâ anlamlıdır
     (1. kategoriden farkı budur).

## Rapor katmanı
Veri katmanı (EDGAR/yfinance/Finnhub'dan çekilen ham ve türetilmiş
metrikler) tüm metrikleri KOŞULSUZ hesaplar; çıktı JSON'u sektör veya
kapsam gerekçesiyle eksiltilmez, her zaman eksiksiz kalır.

Gizleme SADECE render (HTML rapor üretimi) aşamasında yapılır, veri
katmanında değil. Üç gizleme kuralı BAĞIMSIZ çalışır — biri diğerinin
yerine geçmez, bir metrik hangisiyle eşleşirse o gerekçeyle gizlenir
(sıra: SEKTÖR → FİNANSMAN KOLU → KAPSAM):

- SEKTÖR KURALI: sektör banka, sigorta veya GYO ise borç ve marj
  temelli metrikler render'da gizlenir; nedeni raporda tek cümleyle
  belirtilir (bkz. Metrikler > SEKTÖR İSTİSNASI, 1. kategori).
- FİNANSMAN KOLU KURALI: şirket künyesinde finansman/kredi segmenti
  ifadesi geçiyorsa P/FCF ve EV/EBITDA render'da gizlenir; nedeni
  raporda tek cümleyle belirtilir (bkz. Metrikler > SEKTÖR İSTİSNASI,
  2. kategori).
- KAPSAM KURALI: bir metrik, bulunan çeyreklerin %30'undan azında
  doluysa render'da gizlenir; nedeni raporda tek cümleyle belirtilir.

Bu üç kural render katmanında UYGULANMIŞ durumda (bkz. stock_analysis/render.py).

## Tasarım
Mobil öncelikli, dark mode varsayılan, light varyant.
CSS değişken isimleri mugiatama34.github.io reposundaki index.html ile
aynı olmalı. Yeni isim uydurma.
Grafikler için dış CDN kullanma; inline SVG üret.

## Yapma
- Eksik veriyi doldurma, tahmin etme.
- Rapora yorum cümlesi, değerlendirme, sonuç bölümü ekleme.
- Metrik listesine kendiliğinden ekleme yapma.
