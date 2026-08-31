import json
import os
from collections import defaultdict
from datetime import date

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


def resolve_duration_quarters(entries: list) -> dict:
    """Ham SEC fact kayitlarindan (birden fazla etiketten gelmis ve
    _load_priority_entries ile isaretlenmis olabilir) (fiscal_year, "Qn") ->
    {"value", "end", "filed", "form", "derived", "tag"} sozlugu uretir.

    Mantik:
    - Q1: kumulatif zaten ceyregin kendisi (start = mali yil baslangici).
      Sure ~70-110 gun disindaki kayitlar (yanlis fy/fp etiketlenmis olabilir)
      elenir.
    - Q2/Q3: ayrik 3 aylik kayit varsa (sure ~70-100 gun) dogrudan kullanilir;
      yoksa kumulatif kayittan (6/9 aylik) onceki ceyreklerin toplami
      cikarilarak turetilir.
    - Q4: dogrudan hicbir zaman gelmez (10-K sadece yillik verir). Yillik
      toplamdan Q1+Q2+Q3 cikarilarak turetilir. Onceki ceyreklerden biri
      eksikse Q4 de "veri yok" kalir. Q1/Q2/Q3 farkli etiketlerden gelmis
      olsa bile (sirket etiket degistirmisse) turetme calisir, cunku
      birlestirme _load_priority_entries asamasinda zaten yapildi.
    """
    filed_entries = [
        e
        for e in entries
        if e.get("form", "").startswith("10-Q") or e.get("form", "").startswith("10-K")
    ]
    filed_entries = _dedupe_entries(filed_entries)

    by_fy_fp = defaultdict(lambda: defaultdict(list))
    for e in filed_entries:
        fy = e.get("fy")
        fp = e.get("fp")
        if fy is None or fp is None or "start" not in e:
            continue
        by_fy_fp[fy][fp].append(e)

    result = {}
    for fy, by_fp in by_fy_fp.items():
        resolved_values = {}

        q1_entries = [e for e in by_fp.get("Q1", []) if 70 <= _days(e) <= 110]
        if q1_entries:
            e = max(q1_entries, key=lambda x: x["filed"])
            resolved_values["Q1"] = e["val"]
            result[(fy, "Q1")] = {
                "value": e["val"], "end": e["end"], "filed": e["filed"],
                "form": e["form"], "derived": False, "tag": e.get("_tag"),
            }

        for fp_label, prior_labels in (("Q2", ("Q1",)), ("Q3", ("Q1", "Q2"))):
            fp_entries = by_fp.get(fp_label, [])
            if not fp_entries:
                continue
            discrete = [e for e in fp_entries if 70 <= _days(e) <= 100]
            cumulative = [e for e in fp_entries if _days(e) > 100]
            if discrete:
                e = max(discrete, key=lambda x: x["filed"])
                resolved_values[fp_label] = e["val"]
                result[(fy, fp_label)] = {
                    "value": e["val"], "end": e["end"], "filed": e["filed"],
                    "form": e["form"], "derived": False, "tag": e.get("_tag"),
                }
            elif cumulative and all(k in resolved_values for k in prior_labels):
                e = max(cumulative, key=lambda x: x["filed"])
                prior_total = sum(resolved_values[k] for k in prior_labels)
                value = e["val"] - prior_total
                resolved_values[fp_label] = value
                result[(fy, fp_label)] = {
                    "value": value, "end": e["end"], "filed": e["filed"],
                    "form": e["form"], "derived": True, "tag": e.get("_tag"),
                }

        fy_entries = [
            e for e in by_fp.get("FY", [])
            if e.get("form", "").startswith("10-K") and _days(e) > 300
        ]
        if fy_entries and all(k in resolved_values for k in ("Q1", "Q2", "Q3")):
            e = max(fy_entries, key=lambda x: x["filed"])
            prior_total = resolved_values["Q1"] + resolved_values["Q2"] + resolved_values["Q3"]
            value = e["val"] - prior_total
            result[(fy, "Q4")] = {
                "value": value, "end": e["end"], "filed": e["filed"],
                "form": e["form"], "derived": True, "tag": e.get("_tag"),
            }

    return result


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
        resolved = resolve_duration_quarters(combined_raw)
        if resolved:
            duration_results[metric] = resolved

    all_keys = set()
    for quarters in duration_results.values():
        all_keys |= set(quarters.keys())

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
        # adedinden hesaplanir (bkz. config.py notu, madde 5).
        net_income = metrics["net_income"]["value"]
        diluted_shares = metrics["diluted_shares"]["value"]
        eps_value = None
        if net_income is not None and diluted_shares:
            eps_value = net_income / diluted_shares
        metrics["eps_diluted"] = {"value": eps_value, "tag": None, "derived": True}

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
