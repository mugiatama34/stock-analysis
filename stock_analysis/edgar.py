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
    """Ayni (start, end) donemi icin birden fazla kayit varsa (restatement
    vb.), en son 'filed' tarihli olani tutar."""
    best = {}
    for e in entries:
        key = (e.get("start"), e["end"])
        cur = best.get(key)
        if cur is None or e.get("filed", "") >= cur.get("filed", ""):
            best[key] = e
    return list(best.values())


def _days(entry: dict) -> int:
    start = date.fromisoformat(entry["start"])
    end = date.fromisoformat(entry["end"])
    return (end - start).days


def resolve_duration_quarters(entries: list) -> dict:
    """Tek bir tag'e ait ham SEC fact kayitlarindan (fiscal_year, "Qn") ->
    {"value", "end", "filed", "form", "derived"} sozlugu uretir.

    Mantik:
    - Q1: kumulatif zaten ceyregin kendisi (start = mali yil baslangici).
    - Q2/Q3: ayrik 3 aylik kayit varsa (sure ~70-100 gun) dogrudan kullanilir;
      yoksa kumulatif kayittan (6/9 aylik) onceki ceyreklerin toplami
      cikarilarak turetilir.
    - Q4: dogrudan hicbir zaman gelmez (10-K sadece yillik verir). Yillik
      toplamdan Q1+Q2+Q3 cikarilarak turetilir. Onceki ceyreklerden biri
      eksikse Q4 de "veri yok" kalir.
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

        q1_entries = by_fp.get("Q1", [])
        if q1_entries:
            e = max(q1_entries, key=lambda x: x["filed"])
            resolved_values["Q1"] = e["val"]
            result[(fy, "Q1")] = {
                "value": e["val"], "end": e["end"], "filed": e["filed"],
                "form": e["form"], "derived": False,
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
                    "form": e["form"], "derived": False,
                }
            elif cumulative and all(k in resolved_values for k in prior_labels):
                e = max(cumulative, key=lambda x: x["filed"])
                prior_total = sum(resolved_values[k] for k in prior_labels)
                value = e["val"] - prior_total
                resolved_values[fp_label] = value
                result[(fy, fp_label)] = {
                    "value": value, "end": e["end"], "filed": e["filed"],
                    "form": e["form"], "derived": True,
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
                "form": e["form"], "derived": True,
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


_CANONICAL_METRIC_ORDER = (
    "revenue", "net_income", "operating_income", "operating_cash_flow", "eps_diluted",
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
        for tag in tags:
            raw = _load_fact_entries(companyfacts, tag)
            if not raw:
                continue
            resolved = resolve_duration_quarters(raw)
            if resolved:
                duration_results[metric] = {"tag": tag, "quarters": resolved}
                break

    all_keys = set()
    for info in duration_results.values():
        all_keys |= set(info["quarters"].keys())

    new_quarters = {}
    for fy, fp in sorted(all_keys):
        qkey_str = f"{fy}-{fp}"
        if qkey_str in cached_quarters:
            continue

        period_end = filed = form = None
        for metric in _CANONICAL_METRIC_ORDER:
            info = duration_results.get(metric)
            if info and (fy, fp) in info["quarters"]:
                rf = info["quarters"][(fy, fp)]
                period_end, filed, form = rf["end"], rf["filed"], rf["form"]
                break
        if period_end is None:
            for info in duration_results.values():
                if (fy, fp) in info["quarters"]:
                    rf = info["quarters"][(fy, fp)]
                    period_end, filed, form = rf["end"], rf["filed"], rf["form"]
                    break

        metrics = {}
        for metric in config.DURATION_TAG_PRIORITIES:
            info = duration_results.get(metric)
            rf = info["quarters"].get((fy, fp)) if info else None
            if rf is None:
                metrics[metric] = {"value": None, "tag": None, "derived": False}
            else:
                metrics[metric] = {"value": rf["value"], "tag": info["tag"], "derived": rf["derived"]}

        for metric, tags in config.INSTANT_TAG_PRIORITIES.items():
            value = tag_used = None
            if period_end:
                for tag in tags:
                    raw = _load_fact_entries(companyfacts, tag)
                    if not raw:
                        continue
                    resolved = resolve_instant_values(raw, {period_end})
                    if period_end in resolved:
                        value = resolved[period_end]["val"]
                        tag_used = tag
                        break
            metrics[metric] = {"value": value, "tag": tag_used, "derived": False}

        new_quarters[qkey_str] = {
            "fiscal_year": fy,
            "fiscal_quarter": int(fp[1]),
            "period_end": period_end,
            "form": form,
            "filed": filed,
            "metrics": metrics,
        }

    return new_quarters
