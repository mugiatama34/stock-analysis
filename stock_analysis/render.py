"""output/TICKER.json'dan reports/TICKER.html uretir.

Bu asama sadece HTML iskeleti ve sayisal bolumler icindir - grafik yok,
indeks sayfasi yok (bkz. CLAUDE.md > Rapor katmani).

Gizleme mimarisi (CLAUDE.md): UC kural BAGIMSIZ calisir, veri katmani
(pipeline/metrics) hicbir metrigi eksiltmez - gizleme SADECE burada,
render sirasinda yapilir:
  - SEKTOR KURALI: sektor banka/sigorta/GYO ise borc ve marj temelli
    metrikler (bkz. _SECTOR_HIDDEN_METRICS) gizlenir.
  - FINANSMAN KOLU KURALI: sirket kunyesinde finansman/kredi segmenti
    ifadesi geciyorsa (bkz. metrics.classify_financing_arm) P/FCF ve
    EV/EBITDA gizlenir (bkz. _FINANCING_ARM_HIDDEN_METRICS) - bu
    sirketlerde finansman kolu nakit akisini ve borcu bozar, ama sirketin
    kendi marj/borc oranlari (sektor kuralindan farkli olarak) hala
    anlamlidir.
  - KAPSAM KURALI: bir ceyreklik-seri metrigi, bulunan ceyreklerin
    %30'undan azinda doluysa gizlenir (bkz. _COVERAGE_CHECKED_METRICS).
Bir metrik birden fazla kuralla eslesirse SEKTOR -> FINANSMAN KOLU -> KAPSAM
sirasiyla ilk eslesen gerekce kullanilir; gizlenen her metrigin hucresine
"—" konur, gerekce cumlesi hucreye degil bolumun altina TEK SEFERLIK not
olarak yazilir (bkz. _add_note/_render_notes) - ayni gerekce birden fazla
metrigi gizlese bile tekrarlanmaz.

Ayrica F/K ve P/FCF icin ayri bir durum var: TTM net kar (F/K) veya TTM FCF
(P/FCF) <=0 ise bu bir "gizleme" degil - oran metrics.compute_valuation_ratios
tarafindan HIC HESAPLANMAZ (bkz. o modulun docstring'i) ve "unavailable_reasons"
altinda isaretlenir; render bunu "veri yok" ile karistirmadan "hesaplanamaz
(zarar)" olarak gosterir (bkz. _render_valuation, _render_peers).

Genel bir baska ayrim (tek bir kategoriye ozel degil, bkz.
metrics.quarter_reporting_status): bir ceyreklik-seri metrigi son ceyrekte
"veri yok" gorunuyorsa, bu hic veri bulunamadigi icin mi, yoksa sirket bu
kalemi belirli bir ceyrekten sonra ARTIK AYRI RAPORLAMADIGI icin mi net
degil - ikisi kullaniciya farkli anlam tasir. _cell bu ikisini _reporting_gap_label
ile ayirir (orn. Ford total_debt/net_debt: DebtAndCapitalLeaseObligations son
kez 2020-Q4 icin veri donmus, seri 2026-Q1'e kadar gidiyor).
"""

import html
import re

from . import config, metrics, sector_labels

_SUMMARY_TRUNCATE_LIMIT = 400
_SENTENCE_END_RE = re.compile(r"[.!?](?=\s|$)")

_VALUATION_LABELS = {"pe": "F/K", "ps": "P/S", "ev_ebitda": "EV/EBITDA", "p_fcf": "P/FCF"}

# Borc ve marj temelli metrikler - CLAUDE.md > Metrikler > SEKTOR ISTISNASI.
# net_margin BILEREK burada YOK: bankalarda net kar / toplam gelir anlamli
# bir orandir, gizlenmez. F/K de burada yok - degerlemenin kendisi borc/marj
# temelli degildir.
_SECTOR_HIDDEN_METRICS = {
    "gross_margin",
    "operating_margin",
    "net_debt",
    "total_debt",
    "net_debt_to_ebitda",
    "ev_ebitda",
    "p_fcf",
    "interest_coverage",
}

# FINANSMAN KOLU KURALI (CLAUDE.md > Metrikler > SEKTOR ISTISNASI ucuncu
# kategori): SADECE nakit akisi/borc AGIRLIKLI degerleme oranlari gizlenir -
# sirketin kendi marj/borc metrikleri (_SECTOR_HIDDEN_METRICS'in aksine)
# hala anlamlidir, bu yuzden ayri ve daha dar bir kume.
_FINANCING_ARM_HIDDEN_METRICS = {
    "ev_ebitda",
    "p_fcf",
}

# KAPSAM KURALI sadece ceyrek bazinda bir seri olarak var olan ve bu
# render'da GERCEKTEN gosterilen metrikler icin uygulanir. Degerleme
# oranlari (pe/ps/p_fcf) boyle bir ceyreklik seriye sahip degil - kendi
# eksikligi zaten valuation["available"]/valuation_context ile ifade
# edilir, bu yuzden burada yoklar.
_COVERAGE_CHECKED_METRICS = {
    "revenue",
    "net_income",
    "gross_margin",
    "operating_margin",
    "net_margin",
    "fcf",
    "net_debt",
}


def _esc(value) -> str:
    return html.escape(str(value))


def _sorted_quarter_items(quarters: dict) -> list:
    items = [(k, v) for k, v in quarters.items() if v.get("period_end")]
    items.sort(key=lambda kv: kv[1]["period_end"])
    return items


def _quarter_value(quarter: dict, key: str):
    if key in quarter.get("metrics", {}):
        return quarter["metrics"][key]["value"]
    if key in quarter.get("derived_metrics", {}):
        return quarter["derived_metrics"][key]
    return None


def _coverage(quarters: dict, key: str) -> float:
    values = [_quarter_value(q, key) for q in quarters.values()]
    if not values:
        return 0.0
    return sum(1 for v in values if v is not None) / len(values)


def _sector_reason(key: str, data: dict):
    if key in _SECTOR_HIDDEN_METRICS and data["sector_flag"]["is_financial_sector"]:
        return data["sector_flag"]["reason"]
    return None


def _financing_arm_reason(key: str, data: dict):
    flag = data.get("financing_arm_flag", {})
    if key in _FINANCING_ARM_HIDDEN_METRICS and flag.get("has_financing_arm"):
        return flag.get("reason")
    return None


def _hidden_reason(key: str, data: dict):
    reason = _sector_reason(key, data)
    if reason:
        return reason
    reason = _financing_arm_reason(key, data)
    if reason:
        return reason
    if key in _COVERAGE_CHECKED_METRICS:
        coverage = _coverage(data["quarters"], key)
        if coverage < config.RENDER_COVERAGE_THRESHOLD:
            return (
                f"Bu metrik bulunan çeyreklerin %{coverage * 100:.0f}'inde mevcut "
                f"(%{config.RENDER_COVERAGE_THRESHOLD * 100:.0f} eşiğinin altında)."
            )
    return None


def _fmt_ratio(value) -> str:
    return f"{value:.2f}"


def _fmt_percent(value) -> str:
    return f"%{value * 100:.1f}"


def _fmt_percent_raw(value) -> str:
    """Finnhub /stock/metric marj alanlari (grossMarginTTM vb.) zaten yuzde
    olceginde gelir (orn. 45.2 = %45.2) - kendi hesapladigimiz oran
    (0-1 arasi fraksiyon) ile karistirilmamali, bu yuzden _fmt_percent'in
    aksine 100 ile CARPILMAZ."""
    return f"%{value:.1f}"


def _fmt_money(value) -> str:
    sign = "-" if value < 0 else ""
    magnitude = abs(value)
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if magnitude >= threshold:
            return f"{sign}${magnitude / threshold:.2f}{suffix}"
    return f"{sign}${magnitude:,.0f}"


def _fmt_int(value) -> str:
    return f"{int(value):,}"


def _add_note(notes: list, reason: str) -> None:
    """Bir gerekce metnini, zaten listede yoksa siraya ekler. Bu, ayni
    gerekcenin birden fazla hucrede (orn. sektor kurali birden fazla
    metrigi ayni cumleyle gizler) tekrar tekrar yazilmasini onler - hucreye
    sadece '—' konur, gerekce bolumun altinda tek seferlik not olarak
    gosterilir (bkz. modul docstring'i)."""
    if reason not in notes:
        notes.append(reason)


def _render_notes(notes: list) -> str:
    if not notes:
        return ""
    paragraphs = "".join(f'<p class="reason-note">{_esc(r)}</p>' for r in notes)
    return f'<div class="notes">{paragraphs}</div>'


def _valuation_unavailable_reason(data: dict, key: str):
    """F/K veya P/FCF zarar yuzunden hic hesaplanmadiysa (bkz.
    metrics.compute_valuation_ratios) bunun icin isaretlenmis "hesaplanamaz
    (zarar)" metnini dondurur - "veri yok" ile karistirilmamali (biri
    "elimizde deger yok", digeri "bu deger tanimsiz")."""
    return data.get("valuation", {}).get("unavailable_reasons", {}).get(key)


def _reporting_gap_label(data: dict, key: str) -> str:
    """"veri yok" ile "sirket bunu artik ayri raporlamiyor" arasindaki genel
    ayrimi metne cevirir (bkz. metrics.quarter_reporting_status, modul
    docstring'i). Tek bir sektor/kategoriye ozel degildir - herhangi bir
    ceyreklik-seri metrik icin gecerlidir."""
    status = metrics.quarter_reporting_status(data.get("quarters", {}), key)
    if status["status"] == "stopped":
        return (
            f"Şirket bu kalemi {status['last_filled_year']} sonrasında SEC "
            "dosyalamalarında ayrı olarak raporlamıyor."
        )
    return "veri yok"


def _cell(data: dict, key: str, raw_value, formatter, notes: list, missing_label: str = None) -> str:
    reason = _hidden_reason(key, data)
    if reason:
        _add_note(notes, reason)
        return '<span class="hidden-cell">—</span>'
    if raw_value is None:
        return f'<span class="missing">{_esc(missing_label or _reporting_gap_label(data, key))}</span>'
    return formatter(raw_value)


def _field(label: str, value_html: str) -> str:
    return f'<div class="field"><span class="field__label">{_esc(label)}</span><span class="field__value">{value_html}</span></div>'


def _split_summary(text: str, limit: int = _SUMMARY_TRUNCATE_LIMIT):
    """Metin limit'ten kisaysa oldugu gibi (rest=None) dondurulur. Uzunsa,
    ilk limit karakter icinde en son cumle sonu (./!/? + bosluk ya da metin
    sonu) noktasinda kesilir; boyle bir sinir yoksa (tek cumle limit'ten
    uzun) sert kesim yapilip "…" eklenir. Kesilen kisim "rest" olarak
    ayrica dondurulur - "devamini goster" bagi altinda gosterilmek uzere."""
    if len(text) <= limit:
        return text, None

    window = text[:limit]
    cut = None
    for match in _SENTENCE_END_RE.finditer(window):
        cut = match.end()

    if cut is None:
        return window.rstrip() + "…", text[limit:].strip()
    return window[:cut], text[cut:].strip()


def _render_header(data: dict) -> str:
    quarter_items = _sorted_quarter_items(data["quarters"])
    if quarter_items:
        first_q, last_q = quarter_items[0][1], quarter_items[-1][1]
        range_text = (
            f"{first_q['fiscal_year']}-Q{first_q['fiscal_quarter']} – "
            f"{last_q['fiscal_year']}-Q{last_q['fiscal_quarter']}"
        )
        data_date = last_q["period_end"]
    else:
        range_text = "veri yok"
        data_date = "veri yok"

    sector = sector_labels.translate_sector(data.get("sector")) or "veri yok"
    return f"""
<header class="header">
  <h1>{_esc(data['company_name'] or data['ticker'])} <span class="ticker">{_esc(data['ticker'])}</span></h1>
  <div class="header__meta">
    <span>{_esc(sector)}</span>
    <span>Kapsanan çeyrekler: {_esc(range_text)}</span>
    <span>Veri son çeyrek: {_esc(data_date)}</span>
    <span>Rapor üretim tarihi: {_esc(data['generated_at'])}</span>
  </div>
</header>
"""


def _render_summary(summary: str) -> str:
    short, rest = _split_summary(summary)
    if rest is None:
        return f'<p class="summary">{_esc(short)}</p>'
    return (
        f'<p class="summary">{_esc(short)}</p>'
        '<details class="summary-more">'
        "<summary>Devamını göster</summary>"
        f'<p class="summary">{_esc(rest)}</p>'
        "</details>"
    )


def _render_profile(data: dict) -> str:
    summary = data.get("business_summary") or "veri yok"
    sector = sector_labels.translate_sector(data.get("sector"))
    industry = sector_labels.translate_industry(data.get("industry"))
    fields = "".join(
        [
            _field("Sektör", _esc(sector or "veri yok")),
            _field("Endüstri", _esc(industry or "veri yok")),
            _field(
                "Çalışan sayısı",
                _fmt_int(data["employees"]) if data.get("employees") is not None else "veri yok",
            ),
            _field(
                "Piyasa değeri",
                _fmt_money(data["market_cap"]) if data.get("market_cap") is not None else "veri yok",
            ),
        ]
    )
    return f"""
<section class="section">
  <h2>Şirket künyesi</h2>
  {_render_summary(summary)}
  <div class="fields">{fields}</div>
</section>
"""


def _render_valuation(data: dict) -> str:
    valuation = data.get("valuation", {})
    if not valuation.get("available"):
        reason = valuation.get("reason", "veri yok")
        return f"""
<section class="section">
  <h2>Değerleme</h2>
  <p class="reason">{_esc(reason)}</p>
</section>
"""

    context = data.get("valuation_context", {})
    rows = []
    notes = []
    for key, label in _VALUATION_LABELS.items():
        reason = _hidden_reason(key, data)
        value = valuation.get(key)
        if reason:
            _add_note(notes, reason)
            body = '<span class="hidden-cell">—</span>'
        elif value is None:
            missing_text = _valuation_unavailable_reason(data, key) or "veri yok"
            body = f'<span class="missing">{_esc(missing_text)}</span>'
        else:
            ctx = context.get(key, {"status": "no_data", "quarters_used": 0})
            if ctx["status"] == "ok":
                extra = f" — 5 yıllık aralıkta {ctx['percentile']:.0f}. yüzdelik ({ctx['quarters_used']} çeyrek)"
            elif ctx["status"] == "insufficient_history":
                extra = (
                    f" — yüzdelik için asgari {config.VALUATION_HISTORY_MIN_QUARTERS} çeyrek gerekir "
                    f"({ctx['quarters_used']} çeyrek mevcut, ham oran gösteriliyor)"
                )
            else:
                extra = " — geçmiş seri yok, ham oran gösteriliyor"
            body = f"{_fmt_ratio(value)}<span class='context'>{_esc(extra)}</span>"
        rows.append(f'<div class="field"><span class="field__label">{_esc(label)}</span><span class="field__value">{body}</span></div>')

    return f"""
<section class="section">
  <h2>Değerleme</h2>
  <div class="fields">{''.join(rows)}</div>
  {_render_notes(notes)}
</section>
"""


_PEER_ROWS = (
    ("pe", "F/K", "pe_ttm", "pe"),
    ("ps", "P/S", "ps_ttm", "ps"),
    ("gross_margin", "Brüt marj", "gross_margin_ttm", None),
    ("operating_margin", "Faaliyet marj", "operating_margin_ttm", None),
    ("net_margin", "Net marj", "net_margin_ttm", None),
)


def _own_peer_row_value(row_key: str, valuation_key, data: dict, last_quarter):
    if valuation_key is not None:
        return data.get("valuation", {}).get(valuation_key) if data.get("valuation", {}).get("available") else None
    if last_quarter is None:
        return None
    return _quarter_value(last_quarter, row_key)


def _render_peers(data: dict) -> str:
    peers_block = data.get("peers", {})
    if peers_block.get("status") != "ok":
        reason = peers_block.get("reason", "veri alınamadı")
        return f"""
<section class="section">
  <h2>Rakip karşılaştırma</h2>
  <p class="reason">Rakip verisi alınamadı: {_esc(reason)}</p>
</section>
"""

    peers = peers_block.get("peers", [])
    if not peers:
        return """
<section class="section">
  <h2>Rakip karşılaştırma</h2>
  <p class="reason">Rakip bulunamadı.</p>
</section>
"""

    quarter_items = _sorted_quarter_items(data["quarters"])
    last_quarter = quarter_items[-1][1] if quarter_items else None

    header_cells = "".join(f'<th>{_esc(p["ticker"])}</th>' for p in peers)
    body_rows = []
    notes = []
    for row_key, label, finnhub_field, valuation_key in _PEER_ROWS:
        own_value = _own_peer_row_value(row_key, valuation_key, data, last_quarter)
        own_cell = _cell(
            data,
            row_key,
            own_value,
            _fmt_percent if valuation_key is None else _fmt_ratio,
            notes,
            missing_label=_valuation_unavailable_reason(data, valuation_key) if valuation_key else None,
        )
        peer_cells = []
        for peer in peers:
            if peer.get("status") != "ok":
                peer_cells.append('<td><span class="missing">veri alınamadı</span></td>')
                continue
            # KAPSAM KURALI burada uygulanmaz: Finnhub rakip kesiti anlik bir
            # nokta veridir, "bulunan ceyreklerin %X'i" gibi bir seriye
            # sahip degildir - sadece SEKTOR KURALI (varsa) rakip
            # hucrelerine de uygulanir.
            reason = _sector_reason(row_key, data)
            peer_value = peer.get(finnhub_field)
            if reason:
                _add_note(notes, reason)
                peer_cells.append('<td><span class="hidden-cell">—</span></td>')
            elif peer_value is None:
                peer_cells.append('<td><span class="missing">veri yok</span></td>')
            else:
                fmt = _fmt_ratio if valuation_key is not None else _fmt_percent_raw
                peer_cells.append(f"<td>{fmt(peer_value)}</td>")
        body_rows.append(
            f'<tr><td>{_esc(label)}</td><td class="self">{own_cell}</td>{"".join(peer_cells)}</tr>'
        )

    return f"""
<section class="section">
  <h2>Rakip karşılaştırma</h2>
  <table class="peer-table">
    <thead><tr><th>Metrik</th><th class="self">{_esc(data['ticker'])}</th>{header_cells}</tr></thead>
    <tbody>{''.join(body_rows)}</tbody>
  </table>
  {_render_notes(notes)}
</section>
"""


_LATEST_QUARTER_ROWS = (
    ("revenue", "Gelir", _fmt_money),
    ("net_income", "Net kâr", _fmt_money),
    ("fcf", "Serbest nakit akışı (FCF)", _fmt_money),
    ("gross_margin", "Brüt marj", _fmt_percent),
    ("operating_margin", "Faaliyet marjı", _fmt_percent),
    ("net_margin", "Net marj", _fmt_percent),
    ("net_debt", "Net borç", _fmt_money),
)


def _render_latest_quarter(data: dict) -> str:
    quarter_items = _sorted_quarter_items(data["quarters"])
    if not quarter_items:
        return """
<section class="section">
  <h2>Son çeyrek özeti</h2>
  <p class="reason">Veri yok.</p>
</section>
"""

    last_quarter = quarter_items[-1][1]
    label = f"{last_quarter['fiscal_year']}-Q{last_quarter['fiscal_quarter']} ({last_quarter['period_end']})"

    notes = []
    fields = "".join(
        _field(row_label, _cell(data, key, _quarter_value(last_quarter, key), formatter, notes))
        for key, row_label, formatter in _LATEST_QUARTER_ROWS
    )
    return f"""
<section class="section">
  <h2>Son çeyrek özeti</h2>
  <p class="summary">{_esc(label)}</p>
  <div class="fields">{fields}</div>
  {_render_notes(notes)}
</section>
"""


_STYLE = """
:root {
  --bg: #0e0f11;
  --surface: #1a1c1f;
  --text: #f2f2f2;
  --text-muted: #a0a4ab;
  --accent: #6ea8fe;
  --border: #2c2f34;

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 16px;
  --space-4: 24px;

  --radius: 12px;

  --font-size-base: 1rem;
  --font-size-lg: 1.25rem;
}

@media (prefers-color-scheme: light) {
  :root {
    --bg: #f7f7f8;
    --surface: #ffffff;
    --text: #1a1a1a;
    --text-muted: #5b5f66;
    --accent: #2563eb;
    --border: #e0e1e4;
  }
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  font-size: var(--font-size-base);
  line-height: 1.4;
}

main {
  max-width: 720px;
  margin: 0 auto;
  padding: var(--space-4) var(--space-3);
}

.header h1 {
  font-size: var(--font-size-lg);
  margin: 0 0 var(--space-2);
}

.header .ticker {
  color: var(--text-muted);
  font-weight: normal;
}

.header__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-3);
  color: var(--text-muted);
  font-size: 0.9rem;
  margin-bottom: var(--space-4);
}

.section {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-3);
  margin-bottom: var(--space-3);
}

.section h2 {
  font-size: var(--font-size-base);
  margin: 0 0 var(--space-3);
  color: var(--accent);
}

.summary {
  color: var(--text-muted);
  margin: 0 0 var(--space-3);
}

.summary-more summary {
  cursor: pointer;
  color: var(--accent);
  font-size: 0.9rem;
  margin: 0 0 var(--space-2);
}

.summary-more .summary {
  margin: 0;
}

.fields {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.field {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--border);
}

.field:last-child { border-bottom: none; }

.field__label {
  color: var(--text-muted);
}

.field__value {
  text-align: right;
}

.context {
  display: block;
  color: var(--text-muted);
  font-size: 0.85rem;
}

.reason {
  color: var(--text-muted);
  font-style: italic;
}

.missing {
  color: var(--text-muted);
}

.hidden-cell {
  color: var(--text-muted);
}

.notes {
  margin-top: var(--space-2);
  padding-top: var(--space-2);
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.reason-note {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.85rem;
  font-style: italic;
}

.peer-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}

.peer-table th,
.peer-table td {
  border: 1px solid var(--border);
  padding: var(--space-2);
  text-align: center;
  white-space: normal;
  word-break: break-word;
  font-size: 0.85rem;
}

.peer-table td:not(:first-child) {
  white-space: nowrap;
}

.peer-table th:first-child,
.peer-table td:first-child {
  width: 90px;
  text-align: left;
  color: var(--text-muted);
}

.peer-table .self {
  border-left: 2px solid var(--accent);
  border-right: 2px solid var(--accent);
  font-weight: 600;
}

.peer-table th.self {
  color: var(--accent);
}

@media (max-width: 480px) {
  .peer-table th:nth-child(n + 6),
  .peer-table td:nth-child(n + 6) {
    display: none;
  }
}
"""


def render_report(data: dict, generated_at: str) -> str:
    """data: pipeline.fetch_stock_data ciktisi (output/TICKER.json).
    generated_at: raporun uretildigi tarih (ISO string) - veri katmaninin
    bir parcasi degildir, bu yuzden JSON'dan degil cagiran taraftan gelir."""
    data = dict(data, generated_at=generated_at)
    ticker = _esc(data["ticker"])

    body = "".join(
        [
            _render_header(data),
            _render_profile(data),
            _render_valuation(data),
            _render_peers(data),
            _render_latest_quarter(data),
        ]
    )

    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{ticker} - stock-analysis</title>
<style>{_STYLE}</style>
</head>
<body>
<main>
{body}
</main>
</body>
</html>
"""
