import json
import os
from datetime import date, timedelta

import requests

from . import config, errors

QUARTER_LABELS = ("Q1", "Q2", "Q3", "Q4")


def _sec_headers() -> dict:
    if not config.SEC_USER_AGENT:
        raise errors.SecRequestError("SEC_USER_AGENT ortam degiskeni tanimli degil.")
    return {"User-Agent": config.SEC_USER_AGENT}


def load_ticker_map(force_refresh: bool = False) -> dict:
    """Ticker -> zero-padded CIK esleme sozlugu. Statik SEC dosyasi oldugu
    icin diske ayrica onbelleklenir; her pipeline calistirmasinda tekrar
    indirilmez."""
    cache_path = os.path.join(config.CACHE_DIR, "_ticker_map.json")
    if not force_refresh and os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)

    resp = requests.get(config.SEC_TICKER_MAP_URL, headers=_sec_headers(), timeout=30)
    if resp.status_code != 200:
        raise errors.SecRequestError(
            f"SEC ticker listesi alinamadi: HTTP {resp.status_code}"
        )
    raw = resp.json()
    mapping = {row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in raw.values()}

    os.makedirs(config.CACHE_DIR, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f)
    return mapping


def get_cik(ticker: str) -> str:
    mapping = load_ticker_map()
    cik = mapping.get(ticker.upper())
    if cik is None:
        raise errors.TickerNotFoundError(
            f"'{ticker}' SEC EDGAR ticker listesinde bulunamadi. "
            "ABD disi hisseler desteklenmiyor."
        )
    return cik


def fetch_companyfacts(cik: str) -> dict:
    url = config.SEC_COMPANYFACTS_URL.format(cik=cik)
    resp = requests.get(url, headers=_sec_headers(), timeout=60)
    if resp.status_code != 200:
        raise errors.SecRequestError(
            f"SEC companyfacts alinamadi (CIK {cik}): HTTP {resp.status_code}"
        )
    return resp.json()


def _load_fact_entries(companyfacts: dict, tag: str) -> list:
    concept = companyfacts.get("facts", {}).get("us-gaap", {}).get(tag)
    if not concept:
        return []
    units = concept.get("units", {})
    for unit_key in ("USD", "USD/shares", "shares", "pure"):
        if unit_key in units:
            return units[unit_key]
    for entries in units.values():
        return entries
    return []


def _dedupe_entries(entries: list) -> list:
    """Ayni (start, end) donemi icin birden fazla kayit varsa, tercih
    sirasi: (1) daha yuksek onceligi etiketten gelen (_tag_rank kucuk olan -
    bkz. _load_priority_entries), (2) esitlikte en son 'filed' tarihli olan
    (restatement/duzeltme). Boylece ayni donem birden fazla etikette
    gorunse bile hangi etiketin "kazandigi" sirket genelinde degil,
    her (start,end) icin tutarli sekilde config oncelik sirasina gore
    belirlenir."""
    best = {}
    for e in entries:
        key = (e.get("start"), e["end"])
        cur = best.get(key)
        if cur is None:
            best[key] = e
            continue
        cur_rank = cur.get("_tag_rank", 0)
        e_rank = e.get("_tag_rank", 0)
        if e_rank < cur_rank or (e_rank == cur_rank and e.get("filed", "") >= cur.get("filed", "")):
            best[key] = e
    return list(best.values())


def _days(entry: dict) -> int:
    start = date.fromisoformat(entry["start"])
    end = date.fromisoformat(entry["end"])
    return (end - start).days


def _load_priority_entries(companyfacts: dict, tags: list) -> list:
    """Bir metrigin TUM aday etiketlerinden gelen kayitlari, hangi etiketten
    geldigini (_tag, _tag_rank) isaretleyerek TEK listede birlestirir.
    Sirket zaman icinde etiket degistirmis olabilir (orn. ASC 606 sonrasi
    gelir etiketi); tek etikette durmak gecmisin bir kismini sessizce
    dusurur, bu yuzden hepsi toplanir ve cakisan donemler _dedupe_entries
    icinde oncelik sirasina gore cozulur."""
    combined = []
    for rank, tag in enumerate(tags):
        for e in _load_fact_entries(companyfacts, tag):
            e = dict(e)
            e["_tag"] = tag
            e["_tag_rank"] = rank
            combined.append(e)
    return combined


def _next_day(iso_date: str) -> str:
    return (date.fromisoformat(iso_date) + timedelta(days=1)).isoformat()


def _prev_day(iso_date: str) -> str:
    return (date.fromisoformat(iso_date) - timedelta(days=1)).isoformat()


def _classify_duration(days: int):
    """Bir fact'in sure (gun) uzunlugundan hangi donem TURUNU temsil
    ettigini tahmin eder. fy/fp alanina degil, sadece gercek tarih
    araligina dayanir - bkz. resolve_duration_quarters docstring'i."""
    if 70 <= days <= 110:
        return "quarter"
    if 150 <= days <= 200:
        return "half"
    if 250 <= days <= 299:
        return "three_q"
    if 300 <= days <= 380:
        return "annual"
    return None


def _label_source_entries(entries: list) -> dict:
    """(start, end) -> o donemi ILK raporlayan (en erken 'filed') kayit.
    Etiketleme (fy, fp) icin kullanilir: bir sirket bir donemi henuz
    yasanmadan raporlayamayacagi icin, bir donemi ilk raporlayan filing
    o donemi HER ZAMAN guncel (comparative degil) ceyrek olarak
    raporluyordur - bu yuzden SEC'in o spesifik kayda atadigi fy/fp en
    guvenilir olandir (bkz. resolve_duration_quarters docstring'i)."""
    best = {}
    for e in entries:
        if "start" not in e or "end" not in e:
            continue
        key = (e["start"], e["end"])
        cur = best.get(key)
        if cur is None or e.get("filed", "") < cur.get("filed", ""):
            best[key] = e
    return best


def resolve_duration_quarters(entries: list, allow_q4_derivation: bool = True) -> dict:
    """Ham SEC fact kayitlarindan (birden fazla etiketten gelmis ve
    _load_priority_entries ile isaretlenmis olabilir) (fiscal_year, "Qn") ->
    {"value", "end", "filed", "form", "derived", "tag"} sozlugu uretir.

    allow_q4_derivation=False: Q4, yillik kayittan Q1+Q2+Q3 cikarilarak
    TURETILMEZ; sadece dogrudan raporlanmis bir ceyrek kaydi varsa (nadiren)
    kullanilir, yoksa Q4 sonuc sozluginde hic yer almaz. Bu, AGIRLIKLI
    ORTALAMA (config.AVERAGE_METRICS, orn. diluted_shares) kalemler icindir:
    yillik ortalamadan ilk uc ceyregin ortalamasini cikarmak matematiksel
    olarak gecersizdir (bkz. config.py). Ayrica boyle bir metrik icin,
    yillik (10-K) kaydin kendisi HER ZAMAN (fy, "_annual") anahtari altinda
    da dondurulur - Q4 EPS'in yillik EPS'ten turetilmesi icin gerekli
    (bkz. edgar._resolve_eps_diluted).

    ONEMLI: gruplama SEC'in fy/fp alanina DEGIL, fact'in kendi start/end
    tarihine dayanir. Neden: dogrulama sirasinda gercek AAPL verisinde
    gozlemlendi ki SEC, bir filing'in icindeki KARSILASTIRMALI (bir onceki
    yilin ayni ceyregi) fact'e, o fact'in KENDI donemini degil, o filing'in
    GUNCEL ceyreginin fy/fp degerini atayabiliyor (orn. FY2010 Q1 10-Q'sunda
    yer alan FY2009 Q1 karsilastirma rakami, fy=2010,fp=Q1 olarak
    etiketlenmis). fy/fp'ye guvenerek gruplamak, ayni (fy,fp) anahtarinin
    altinda FARKLI gercek donemlere ait degerlerin cakismasina ve
    birbirini rastgele ezmesine yol aciyordu. fy/fp alani hicbir zaman
    bos/None gelmiyor (bu yuzden eskiden sessizce atlanmiyordu) - deger
    basitce YANLIS oluyordu.

    Mantik (tamamen tarih tabanli):
    - Bir "ceyrek" suresi (70-110 gun) kaydi, ONCESINDE (bitis+1 gun =
      baslangic) baska bir ceyrek kaydi YOKSA yeni bir mali yil dongusunun
      Q1'i sayilir (donguyu "capa"lar).
    - Q2/Q3: capadan sonraki gunde baslayan ayrik bir ceyrek kaydi varsa
      dogrudan kullanilir; yoksa capayla AYNI baslangica sahip kumulatif
      kayittan (6/9 aylik) onceki ceyreklerin toplami cikarilarak turetilir.
    - Q4: capayla ayni baslangica sahip yillik (10-K) kayittan Q1+Q2+Q3
      cikarilarak turetilir. Onceki ceyreklerden biri eksikse zincir orada
      durur, Q4 (ve varsa sonraki adimlar) "veri yok" kalir.
    - Etiket (fy): bu donguyu capalayan Q1 kaydinin (start,end) ciftini
      ILK raporlayan filing'den alinir (_label_source_entries) - fp ise
      zincirdeki pozisyondan (Q1/Q2/Q3/Q4) dogrudan belirlenir, SEC'in
      fp alanina hic bakilmaz.
    """
    filed_entries = [
        e
        for e in entries
        if (e.get("form", "").startswith("10-Q") or e.get("form", "").startswith("10-K"))
        and "start" in e and "end" in e
    ]
    if not filed_entries:
        return {}

    value_entries = _dedupe_entries(filed_entries)
    label_source = _label_source_entries(filed_entries)

    quarter_by_start, half_by_start, three_q_by_start, annual_by_start = {}, {}, {}, {}
    for e in value_entries:
        kind = _classify_duration(_days(e))
        if kind == "quarter":
            quarter_by_start[e["start"]] = e
        elif kind == "half":
            half_by_start[e["start"]] = e
        elif kind == "three_q":
            three_q_by_start[e["start"]] = e
        elif kind == "annual":
            annual_by_start[e["start"]] = e

    known_quarter_ends = {e["end"] for e in quarter_by_start.values()}

    def _mk(value, source_entry, derived):
        return {
            "value": value, "end": source_entry["end"], "filed": source_entry["filed"],
            "form": source_entry["form"], "derived": derived, "tag": source_entry.get("_tag"),
        }

    result = {}
    for s_fy, q1 in quarter_by_start.items():
        if _prev_day(s_fy) in known_quarter_ends:
            continue  # bu bir mali yil baslangici degil, onceki bir ceyregin devami

        chain = {"Q1": _mk(q1["val"], q1, False)}

        q2 = quarter_by_start.get(_next_day(q1["end"]))
        if q2 is None:
            half_e = half_by_start.get(s_fy)
            if half_e is None:
                _emit_cycle(result, s_fy, chain, label_source)
                continue
            chain["Q2"] = _mk(half_e["val"] - chain["Q1"]["value"], half_e, True)
        else:
            chain["Q2"] = _mk(q2["val"], q2, False)

        q3 = quarter_by_start.get(_next_day(chain["Q2"]["end"]))
        if q3 is None:
            three_q_e = three_q_by_start.get(s_fy)
            if three_q_e is None:
                _emit_cycle(result, s_fy, chain, label_source)
                continue
            prior = chain["Q1"]["value"] + chain["Q2"]["value"]
            chain["Q3"] = _mk(three_q_e["val"] - prior, three_q_e, True)
        else:
            chain["Q3"] = _mk(q3["val"], q3, False)

        annual_e = annual_by_start.get(s_fy)
        q4 = quarter_by_start.get(_next_day(chain["Q3"]["end"]))
        if q4 is not None and annual_e is not None and q4["end"] == annual_e["end"]:
            chain["Q4"] = _mk(q4["val"], q4, False)
        elif annual_e is not None and allow_q4_derivation:
            prior = chain["Q1"]["value"] + chain["Q2"]["value"] + chain["Q3"]["value"]
            chain["Q4"] = _mk(annual_e["val"] - prior, annual_e, True)

        if annual_e is not None:
            chain["_annual"] = _mk(annual_e["val"], annual_e, False)

        _emit_cycle(result, s_fy, chain, label_source)

    return result


def _emit_cycle(result: dict, s_fy: str, chain: dict, label_source: dict) -> None:
    """chain'i (Q1..Q4 alt kumesi) sonuc sozluguna yazar. fy etiketi,
    donguyu capalayan Q1'in (start,end) ciftini ILK raporlayan kayittan
    alinir (bkz. resolve_duration_quarters docstring'i); fp ise SEC'in
    fp alanina degil, chain'deki pozisyona (Q1/Q2/Q3/Q4) gore belirlenir."""
    q1_end = chain["Q1"]["end"]
    label_entry = label_source.get((s_fy, q1_end))
    if label_entry is None:
        return
    fy = label_entry.get("fy")
    if fy is None:
        return
    for fp_label, entry in chain.items():
        result[(fy, fp_label)] = entry


def resolve_instant_values(entries: list, wanted_ends: set) -> dict:
    """Bilanco (instant) kalemler icin: verilen ceyrek-sonu tarihlerine denk
    gelen degerleri dogrudan dondurur. Turetme yapilmaz."""
    filed_entries = [
        e
        for e in entries
        if e.get("form", "").startswith("10-Q") or e.get("form", "").startswith("10-K")
    ]
    by_end = {}
    for e in filed_entries:
        if e["end"] not in wanted_ends:
            continue
        cur = by_end.get(e["end"])
        if cur is None or e.get("filed", "") >= cur.get("filed", ""):
            by_end[e["end"]] = e
    return by_end


_CANONICAL_METRIC_ORDER = ("revenue", "net_income", "operating_income", "operating_cash_flow")


def _resolve_instant_metric(companyfacts: dict, tags: list, wanted_ends: set) -> tuple:
    """Bir instant metrigin aday etiketleri icin, sirket genelinde herhangi
    bir deger dondurun ILK etigeti SABIT olarak kullanir ve o etiketle tum
    istenen ceyrek-sonu tarihlerini bir kerede cozer. Duration metriklerin
    aksine burada BIRLESTIRME yapilmaz: config.INSTANT_TAG_PRIORITIES'teki
    etiketler ayni kavramin farkli tanimlari olabilir (orn. LongTermDebt ile
    LongTermDebtNoncurrent), bu yuzden bir sirketin serisi ceyrekten
    ceyrege farkli tanima kaymamali. Donen: (kullanilan_tag, {end: entry})."""
    for tag in tags:
        raw = _load_fact_entries(companyfacts, tag)
        if not raw:
            continue
        resolved = resolve_instant_values(raw, wanted_ends)
        if resolved:
            return tag, resolved
    return None, {}


def _resolve_eps_diluted(duration_results: dict) -> dict:
    """eps_diluted, XBRL etiketinden degil net kar / seyreltilmis hisse
    adedinden hesaplanir (bkz. config.py). Q1-Q3: o ceyregin kendi net kari
    / kendi (dogrudan raporlanmis) seyreltilmis hisse adedi. Q4:
    diluted_shares agirlikli bir ORTALAMA oldugu icin (config.AVERAGE_METRICS)
    yillik toplamdan Q1+Q2+Q3 cikarilarak turetilemez (bkz.
    resolve_duration_quarters) - bunun yerine Q4 EPS = yillik EPS -
    (Q1 EPS + Q2 EPS + Q3 EPS) olarak hesaplanir; yillik EPS de yillik net
    kar (Q1..Q4 toplami) / 10-K'da raporlanan yillik agirlikli ortalama
    hisse adedinden ((fy, "_annual") kaydi) gelir. Herhangi bir bilesen
    eksikse Q4 EPS 'veri yok' kalir, tahmini bir deger uretilmez."""
    net_income_q = duration_results.get("net_income", {})
    diluted_shares_q = duration_results.get("diluted_shares", {})

    fiscal_years = {fy for fy, fp in net_income_q if fp in QUARTER_LABELS}

    eps = {}
    for fy in fiscal_years:
        q_eps = {}
        for fp in ("Q1", "Q2", "Q3"):
            ni = net_income_q.get((fy, fp))
            ds = diluted_shares_q.get((fy, fp))
            if ni is not None and ds is not None and ds["value"]:
                value = ni["value"] / ds["value"]
                q_eps[fp] = value
                eps[(fy, fp)] = value

        ni_q4 = net_income_q.get((fy, "Q4"))
        annual_ds = diluted_shares_q.get((fy, "_annual"))
        if ni_q4 is not None and annual_ds is not None and annual_ds["value"] and len(q_eps) == 3:
            annual_net_income = ni_q4["value"] + sum(
                net_income_q[(fy, fp)]["value"] for fp in ("Q1", "Q2", "Q3")
            )
            annual_eps = annual_net_income / annual_ds["value"]
            eps[(fy, "Q4")] = annual_eps - (q_eps["Q1"] + q_eps["Q2"] + q_eps["Q3"])

    return eps


assert set(config.DURATION_TAG_PRIORITIES) == config.FLOW_METRICS | config.AVERAGE_METRICS, (
    "DURATION_TAG_PRIORITIES'teki her metrik config.FLOW_METRICS veya "
    "config.AVERAGE_METRICS icinde tam olarak bir kez siniflandirilmis olmali."
)


def build_quarters(companyfacts: dict, cached_quarters: dict = None) -> dict:
    """companyfacts JSON'undan, cache'te henuz OLMAYAN ceyrekleri isler ve
    dondurur. cache.py bu sonucu mevcut cache ile birlestirir.

    Not: SEC companyfacts endpoint'i kismi/artimli cekim desteklemiyor; her
    calistirmada tum gecmis tek istekte gelir. "Sadece eksik ceyrekler
    cekilir" burada, zaten cache'te olan ceyreklerin yeniden ISLENMEMESI
    (parse + Q4 turetmesinden gecirilmemesi) olarak uygulanir.
    """
    cached_quarters = cached_quarters or {}

    duration_results = {}
    for metric, tags in config.DURATION_TAG_PRIORITIES.items():
        combined_raw = _load_priority_entries(companyfacts, tags)
        if not combined_raw:
            continue
        resolved = resolve_duration_quarters(
            combined_raw, allow_q4_derivation=metric in config.FLOW_METRICS
        )
        if resolved:
            duration_results[metric] = resolved

    eps_by_key = _resolve_eps_diluted(duration_results)

    # (fy, "_annual") gibi yardimci anahtarlar gercek bir ceyrek degildir,
    # ve config.MIN_FISCAL_YEAR'dan once kalan ceyrekler seriye hic girmez
    # (bkz. config.py notu - orn. AAPL'de tek basina duran 2009-Q1).
    all_keys = set()
    for quarters in duration_results.values():
        all_keys |= {
            (fy, fp)
            for fy, fp in quarters
            if fp in QUARTER_LABELS and fy >= config.MIN_FISCAL_YEAR
        }

    new_keys = [
        (fy, fp) for fy, fp in sorted(all_keys) if f"{fy}-{fp}" not in cached_quarters
    ]

    period_info = {}
    for fy, fp in new_keys:
        period_end = filed = form = None
        for metric in _CANONICAL_METRIC_ORDER:
            quarters = duration_results.get(metric)
            if quarters and (fy, fp) in quarters:
                rf = quarters[(fy, fp)]
                period_end, filed, form = rf["end"], rf["filed"], rf["form"]
                break
        if period_end is None:
            for quarters in duration_results.values():
                if (fy, fp) in quarters:
                    rf = quarters[(fy, fp)]
                    period_end, filed, form = rf["end"], rf["filed"], rf["form"]
                    break
        period_info[(fy, fp)] = (period_end, filed, form)

    wanted_ends = {pe for pe, _, _ in period_info.values() if pe}

    instant_results = {
        metric: _resolve_instant_metric(companyfacts, tags, wanted_ends)
        for metric, tags in config.INSTANT_TAG_PRIORITIES.items()
    }
    additive_results = {
        metric: _resolve_instant_metric(companyfacts, tags, wanted_ends)
        for metric, tags in config.INSTANT_ADDITIVE_TAGS.items()
    }

    new_quarters = {}
    for fy, fp in new_keys:
        qkey_str = f"{fy}-{fp}"
        period_end, filed, form = period_info[(fy, fp)]

        metrics = {}
        for metric in config.DURATION_TAG_PRIORITIES:
            quarters = duration_results.get(metric)
            rf = quarters.get((fy, fp)) if quarters else None
            if rf is None:
                metrics[metric] = {"value": None, "tag": None, "derived": False}
            else:
                metrics[metric] = {"value": rf["value"], "tag": rf.get("tag"), "derived": rf["derived"]}

        # eps_diluted: XBRL etiketinden degil, net kar / seyreltilmis hisse
        # adedinden hesaplanir (bkz. _resolve_eps_diluted).
        metrics["eps_diluted"] = {"value": eps_by_key.get((fy, fp)), "tag": None, "derived": True}

        for metric, (tag_used, resolved) in instant_results.items():
            value = None
            if period_end and period_end in resolved:
                value = resolved[period_end]["val"]
            if value is not None and metric in additive_results:
                _, add_resolved = additive_results[metric]
                add_entry = add_resolved.get(period_end)
                if add_entry is not None:
                    value += add_entry["val"]
            metrics[metric] = {
                "value": value,
                "tag": tag_used if value is not None else None,
                "derived": False,
            }

        new_quarters[qkey_str] = {
            "fiscal_year": fy,
            "fiscal_quarter": int(fp[1]),
            "period_end": period_end,
            "form": form,
            "filed": filed,
            "metrics": metrics,
        }

    return new_quarters
