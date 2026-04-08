#!/usr/bin/env python3
"""
build_dashboard.py
Reads data/history.json, data/trends.json, data/insights.json
and writes a complete self-contained docs/index.html for GitHub Pages.
"""

import json
from pathlib import Path
from datetime import datetime

HISTORY_FILE  = Path(__file__).parent.parent / "data" / "history.json"
TRENDS_FILE   = Path(__file__).parent.parent / "data" / "trends.json"
INSIGHTS_FILE = Path(__file__).parent.parent / "data" / "insights.json"
SUPP_FILE     = Path(__file__).parent.parent / "data" / "supplemental_latest.json"
OUTPUT_FILE   = Path(__file__).parent.parent / "docs" / "index.html"

import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import MARKETS

# ─── Helpers ──────────────────────────────────────────────────────────────────

def fmt_rent(v):
    if v is None: return "—"
    return f"${v:,.0f}"

def fmt_pct(v, show_sign=True):
    if v is None: return "—"
    sign = "+" if v > 0 and show_sign else ""
    return f"{sign}{v:.1f}%"

def fmt_days(v):
    if v is None: return "—"
    return f"{v:.0f}d"

def pct_class(v):
    if v is None: return ""
    return "up" if v > 0 else "down" if v < 0 else ""

def temp_color(temp):
    return {
        "hot": "#e07a6a", "warm": "#f4a235",
        "neutral": "#86b96e", "cool": "#7eb3d4", "cold": "#b99ddb"
    }.get(temp, "#86b96e")


def fmt_date(ts: str, fallback: str = "n/a") -> str:
    if not ts:
        return fallback
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return ts[:10] if len(ts) >= 10 else ts


def source_note_for_bedroom(bedroom: str, supp_market: dict | None) -> str:
    if not supp_market:
        return f"{bedroom}BR: unavailable"

    bd = supp_market.get("bedrooms", {}).get(bedroom, {})
    source = bd.get("source")
    detail = bd.get("source_detail")
    if source == "apartment_list":
        return f"{bedroom}BR: Apartment List ({detail})" if detail else f"{bedroom}BR: Apartment List"
    if source == "zillow_derived":
        return f"{bedroom}BR: Zillow-derived ({detail})" if detail else f"{bedroom}BR: Zillow-derived"
    return f"{bedroom}BR: unavailable"

def insight_paragraphs(text: str) -> str:
    """Convert insight text with HEADER\nParagraph format to HTML."""
    headers = ["MARKET CONDITIONS", "IMPLICATIONS FOR CURRENT OWNERS",
               "VACANCY MARKETING STRATEGY", "RENEWAL PRICING STRATEGY",
               "UPSTATE SC MACRO VIEW",
               "OUTLOOK AND RISKS"]
    html = text.replace("**", "")
    for h in headers:
        html = html.replace(h, f'<h4 class="insight-header">{h}</h4>')
    paras = []
    for chunk in html.split("\n\n"):
        chunk = chunk.strip()
        if not chunk: continue
        if chunk.startswith("<h4"):
            paras.append(chunk)
        else:
            paras.append(f"<p>{chunk}</p>")
    return "\n".join(paras)

# ─── HTML sections ────────────────────────────────────────────────────────────

def build_market_card(mkt_key, trends, insights, supp_market):
    mkt_cfg  = MARKETS[mkt_key]
    mt       = trends["markets"].get(mkt_key, {})
    agg      = mt.get("aggregate", {})
    cond     = mt.get("market_conditions", {})
    beds     = mt.get("bedrooms", {})
    color    = mkt_cfg["color"]
    tc       = temp_color(cond.get("temperature"))

    rent_cur = agg.get("averageRent", {}).get("current")
    rent_mom = agg.get("averageRent", {}).get("changes", {}).get("mom", {}).get("pct_change")
    dom_cur  = agg.get("averageDaysOnMarket", {}).get("current")
    inv_cur  = agg.get("totalListings", {}).get("current")

    bed_rows = ""
    for b in ["1", "2", "3", "4"]:
        bd = beds.get(b, {})
        r  = bd.get("averageRent", {}).get("current")
        d  = bd.get("averageDaysOnMarket", {}).get("current")
        bed_rows += (
            f"<tr><td>{b}BR</td>"
            f"<td>{fmt_rent(r)}</td>"
            f"<td>{fmt_days(d)}</td></tr>"
        )

    market_source_lines = []
    zillow_detail = supp_market.get("zillow_source_detail") if supp_market else None
    if zillow_detail:
        market_source_lines.append(f"Overall cross-check: Zillow ({zillow_detail})")
    else:
        market_source_lines.append("Overall cross-check: Zillow unavailable")
    for b in ["1", "2", "3", "4"]:
        market_source_lines.append(source_note_for_bedroom(b, supp_market))
    source_html = "".join(f"<div>{line}</div>" for line in market_source_lines)

    insight_text = insights.get("markets", {}).get(mkt_key, "")
    insight_html = insight_paragraphs(insight_text) if insight_text else "<p>Analysis not available.</p>"

    tier_badge = (
        '<span class="tier-badge tier-full">Live Data</span>'
        if mkt_cfg["tier"] == "primary"
        else '<span class="tier-badge tier-snap">RentCast</span>'
    )

    return f"""
<div class="market-section" id="mkt-{mkt_key}">
  <div class="market-header" style="border-left: 4px solid {color}">
    <div class="market-title-row">
      <h2 style="color:{color}">{mkt_cfg['name']} {tier_badge}</h2>
      <span class="temp-badge" style="background:{tc}22;color:{tc};border:1px solid {tc}55">
        {cond.get('temperature_label', '—')}
      </span>
    </div>
    <div class="market-label">{mkt_cfg['label']}</div>
  </div>

  <div class="metrics-row">
    <div class="metric-card" style="border-top-color:{color}">
      <div class="metric-label">Avg Rent</div>
      <div class="metric-val">{fmt_rent(rent_cur)}</div>
      <div class="trend-row">
        <span class="trend-item {pct_class(rent_mom)}">MoM {fmt_pct(rent_mom)}</span>
      </div>
    </div>
    <div class="metric-card" style="border-top-color:{color}">
      <div class="metric-label">Days on Market</div>
      <div class="metric-val">{fmt_days(dom_cur)}</div>
      <div class="trend-row"><span class="trend-note">(lower = tighter market)</span></div>
    </div>
    <div class="metric-card" style="border-top-color:{color}">
      <div class="metric-label">Active Listings</div>
      <div class="metric-val">{f'{inv_cur:,.0f}' if inv_cur else '—'}</div>
      <div class="trend-row"><span class="trend-note">(lower = less supply)</span></div>
    </div>
  </div>

  <div class="bedroom-table-wrap">
    <table class="bedroom-table">
      <thead><tr><th>Size</th><th>Avg Rent</th><th>Avg DOM</th></tr></thead>
      <tbody>{bed_rows}</tbody>
    </table>
  </div>

  <div class="source-block">
    <div class="source-label">Market Data Sources</div>
    <div class="source-text">{source_html}</div>
  </div>

  <div class="insight-block">
    <div class="insight-label">AI Market Analysis</div>
    {insight_html}
  </div>
</div>
"""

def build_html(trends, insights, history, supplemental):
    as_of = trends.get("as_of", "")
    as_of_display = datetime.strptime(as_of, "%Y-%m").strftime("%B %Y") if as_of else "—"
    generated = insights.get("generated_at", "")[:10]
    rentcast_fetched = history[-1].get("fetched_at", "") if history else ""
    supplemental_fetched = supplemental.get("fetched_at", "") if supplemental else ""
    months_count = len(history)
    rs = trends.get("regional_summary", {})
    avg_mom = [
        trends["markets"][m]["aggregate"]["averageRent"]["changes"]["mom"]["pct_change"]
        for m in MARKETS
        if trends["markets"][m]["aggregate"]["averageRent"]["changes"]["mom"]["pct_change"] is not None
    ]
    avg_mom_rent = round(sum(avg_mom) / len(avg_mom), 2) if avg_mom else None

    regional_insight = insights.get("regional", "")
    regional_html = insight_paragraphs(regional_insight) if regional_insight else ""

    # Build market sections — primary markets first, then foothills
    primary_sections = ""
    foothills_sections = ""
    for mkt_key, mkt_cfg in MARKETS.items():
        supp_market = supplemental.get("markets", {}).get(mkt_key, {}) if supplemental else {}
        card = build_market_card(mkt_key, trends, insights, supp_market)
        if mkt_cfg["tier"] == "primary":
            primary_sections += card
        else:
            foothills_sections += card

    # Nav links
    nav_links = " · ".join(
        f'<a href="#mkt-{k}">{v["name"]}</a>' for k, v in MARKETS.items()
    )

    hottest = MARKETS.get(rs.get("hottest_market", ""), {}).get("name", "—")
    softest = MARKETS.get(rs.get("softest_market", ""), {}).get("name", "—")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Upstate SC Rental Market — {as_of_display}</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{font-size:15px;scroll-behavior:smooth}}
body{{background:#0d1a14;color:#e8efe0;font-family:'Georgia',serif;line-height:1.6}}
a{{color:#86b96e;text-decoration:none}}
a:hover{{text-decoration:underline}}

.site-header{{background:linear-gradient(170deg,#0a1f10,#0d1a14);border-bottom:1px solid rgba(134,185,110,.18);padding:32px 40px 24px}}
.eyebrow{{font-size:10px;color:#86b96e;letter-spacing:2.5px;text-transform:uppercase;font-family:'Courier New',monospace;margin-bottom:8px}}
h1{{font-size:30px;font-weight:400;color:#f0f5e8;margin-bottom:6px}}
h1 em{{color:#86b96e;font-style:italic}}
.subtitle{{font-size:11px;color:#4a6040;font-family:'Courier New',monospace;margin-bottom:20px}}

.nav-bar{{font-size:12px;color:#4a6040;font-family:sans-serif;padding:12px 40px;background:rgba(0,0,0,.2);border-bottom:1px solid rgba(255,255,255,.04)}}
.nav-bar a{{color:#86b96e;margin-right:4px}}

.hero-stats{{display:flex;flex-wrap:wrap;gap:12px;margin-top:20px}}
.hero-stat{{background:rgba(255,255,255,.04);border-radius:10px;padding:12px 18px;min-width:110px;text-align:center}}
.hs-label{{font-size:10px;color:#4a6040;text-transform:uppercase;letter-spacing:1px;font-family:'Courier New',monospace}}
.hs-val{{font-size:20px;font-weight:800;margin-top:3px;font-family:sans-serif}}

.main{{max-width:1100px;margin:0 auto;padding:32px 40px 60px}}

.section-header{{font-size:11px;color:#86b96e;letter-spacing:2px;text-transform:uppercase;font-family:'Courier New',monospace;margin:40px 0 20px;padding-bottom:8px;border-bottom:1px solid rgba(134,185,110,.2)}}

.regional-block{{background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.07);border-radius:14px;padding:28px;margin-bottom:36px}}
.regional-title{{font-size:16px;color:#f0f5e8;margin-bottom:16px}}
.insight-header{{font-size:11px;color:#86b96e;letter-spacing:1.5px;text-transform:uppercase;font-family:'Courier New',monospace;margin:20px 0 8px}}
.insight-block p{{font-size:14px;color:#b8c8b0;line-height:1.75;margin-bottom:14px;font-family:sans-serif}}

.market-section{{background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:28px;margin-bottom:28px}}
.market-header{{margin-bottom:20px}}
.market-title-row{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:4px}}
.market-title-row h2{{font-size:20px;font-weight:400}}
.market-label{{font-size:11px;color:#4a6040;font-family:'Courier New',monospace}}

.temp-badge{{padding:4px 12px;border-radius:20px;font-size:11px;font-weight:600;font-family:sans-serif}}
.tier-badge{{font-size:9px;padding:2px 8px;border-radius:8px;font-family:'Courier New',monospace;letter-spacing:.5px;vertical-align:middle}}
.tier-full{{background:rgba(134,185,110,.15);color:#86b96e;border:1px solid rgba(134,185,110,.3)}}
.tier-snap{{background:rgba(196,163,110,.15);color:#c4a36e;border:1px solid rgba(196,163,110,.3)}}

.metrics-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:18px}}
.metric-card{{background:rgba(0,0,0,.2);border-radius:10px;padding:14px 16px;border-top:2px solid transparent}}
.metric-label{{font-size:10px;color:#4a6040;text-transform:uppercase;letter-spacing:1px;font-family:'Courier New',monospace;margin-bottom:4px}}
.metric-val{{font-size:24px;font-weight:800;color:#f0f5e8;font-family:sans-serif;margin-bottom:8px}}
.trend-row{{display:flex;flex-wrap:wrap;gap:6px;align-items:center}}
.trend-item{{font-size:11px;font-family:sans-serif;padding:2px 7px;border-radius:6px;font-weight:600}}
.trend-item.up{{background:rgba(134,185,110,.15);color:#86b96e}}
.trend-item.down{{background:rgba(224,122,106,.15);color:#e07a6a}}
.trend-item:not(.up):not(.down){{background:rgba(255,255,255,.05);color:#6a8060}}
.trend-note{{font-size:10px;color:#4a6040;font-family:sans-serif;font-style:italic}}

.bedroom-table-wrap{{overflow-x:auto;margin-bottom:20px}}
.bedroom-table{{width:100%;border-collapse:collapse;font-size:13px;font-family:sans-serif}}
.bedroom-table th{{padding:8px 12px;text-align:right;color:#4a6040;font-weight:600;font-size:10px;letter-spacing:.5px;text-transform:uppercase;border-bottom:1px solid rgba(255,255,255,.07)}}
.bedroom-table th:first-child{{text-align:left}}
.bedroom-table td{{padding:9px 12px;text-align:right;border-bottom:1px solid rgba(255,255,255,.03)}}
.bedroom-table td:first-child{{text-align:left;font-weight:600;color:#9abf80}}
.bedroom-table td.up{{color:#86b96e;font-weight:700}}
.bedroom-table td.down{{color:#e07a6a;font-weight:700}}

.insight-block{{background:rgba(0,0,0,.15);border-radius:10px;padding:22px 24px;border-left:3px solid rgba(134,185,110,.25)}}
.insight-label{{font-size:10px;color:#86b96e;letter-spacing:2px;text-transform:uppercase;font-family:'Courier New',monospace;margin-bottom:14px}}
.source-block{{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:10px;padding:14px 16px;margin-bottom:18px}}
.source-label{{font-size:10px;color:#c4a36e;letter-spacing:2px;text-transform:uppercase;font-family:'Courier New',monospace;margin-bottom:10px}}
.source-text{{font-size:12px;color:#9fb19a;font-family:sans-serif;line-height:1.7}}
.source-refresh{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-bottom:24px}}
.source-refresh-card{{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:10px;padding:14px 16px}}
.source-refresh-name{{font-size:10px;color:#4a6040;text-transform:uppercase;letter-spacing:1px;font-family:'Courier New',monospace;margin-bottom:6px}}
.source-refresh-date{{font-size:16px;color:#f0f5e8;font-family:sans-serif;font-weight:700}}
.source-refresh-note{{font-size:12px;color:#8da18a;font-family:sans-serif;margin-top:4px}}

.data-note{{background:rgba(126,179,212,.07);border:1px solid rgba(126,179,212,.18);border-left:3px solid #7eb3d4;border-radius:8px;padding:14px 18px;margin-bottom:24px;font-size:13px;color:#8ab8d0;font-family:sans-serif;line-height:1.6}}

.footer{{text-align:center;font-size:11px;color:#2a4030;font-family:'Courier New',monospace;margin-top:60px;padding-top:20px;border-top:1px solid rgba(255,255,255,.04)}}

@media(max-width:600px){{
  .site-header,.main,.nav-bar{{padding-left:20px;padding-right:20px}}
  .metrics-row{{grid-template-columns:1fr 1fr}}
}}
</style>
</head>
<body>

<div class="site-header">
  <div class="eyebrow">🏠 Upstate South Carolina · 10 Markets · RentCast Live Data</div>
  <h1>Rental Market <em>Intelligence</em></h1>
  <p class="subtitle">Auto-refreshed monthly · {months_count} months of history · Last updated {generated}</p>
  <div class="hero-stats">
    <div class="hero-stat">
      <div class="hs-label">Report Period</div>
      <div class="hs-val" style="color:#86b96e;font-size:15px">{as_of_display}</div>
    </div>
    <div class="hero-stat">
      <div class="hs-label">Avg MoM Rent</div>
      <div class="hs-val" style="color:{'#86b96e' if (avg_mom_rent or 0) >= 0 else '#e07a6a'}">{fmt_pct(avg_mom_rent)}</div>
    </div>
    <div class="hero-stat">
      <div class="hs-label">Hottest Market</div>
      <div class="hs-val" style="color:#f4a235;font-size:15px">{hottest}</div>
    </div>
    <div class="hero-stat">
      <div class="hs-label">Softest Market</div>
      <div class="hs-val" style="color:#7eb3d4;font-size:15px">{softest}</div>
    </div>
  </div>
</div>

<div class="nav-bar">Jump to: {nav_links}</div>

<div class="main">
  <div class="data-note">
    <strong>📊 Live Data:</strong> Market data pulled monthly from
    <strong>RentCast API</strong> (rentcast.io) covering 18 zip codes across 10 Upstate SC markets.
    Analysis generated by <strong>Claude AI</strong>. Data reflects active rental listings only.
    <strong>Not financial advice.</strong>
  </div>

  <div class="source-refresh">
    <div class="source-refresh-card">
      <div class="source-refresh-name">RentCast Refresh</div>
      <div class="source-refresh-date">{fmt_date(rentcast_fetched)}</div>
      <div class="source-refresh-note">Latest live RentCast pull used for core market metrics</div>
    </div>
    <div class="source-refresh-card">
      <div class="source-refresh-name">Supplemental Refresh</div>
      <div class="source-refresh-date">{fmt_date(supplemental_fetched)}</div>
      <div class="source-refresh-note">Apartment List 1BR/2BR and Zillow-derived bedroom support</div>
    </div>
    <div class="source-refresh-card">
      <div class="source-refresh-name">AI Insight Refresh</div>
      <div class="source-refresh-date">{generated or 'n/a'}</div>
      <div class="source-refresh-note">Latest Claude narrative generation date</div>
    </div>
  </div>

  <div class="section-header">Regional Executive Summary</div>
  <div class="regional-block">
    <div class="regional-title">Upstate South Carolina · {as_of_display}</div>
    <div class="insight-block">
      <div class="insight-label">AI Regional Analysis</div>
      {regional_html}
    </div>
  </div>

  <div class="section-header">Primary Markets</div>
  {primary_sections}

  <div class="section-header">Foothills &amp; Lakes Markets</div>
  {foothills_sections}

  <div class="footer">
    Upstate SC Rental Market Intelligence · Data: RentCast API · Analysis: Claude AI ·
    Auto-refreshed 1st of each month via GitHub Actions · {as_of_display}
  </div>
</div>

</body>
</html>"""

def main():
    print(f"\n{'='*55}")
    print("Dashboard Builder")
    print(f"{'='*55}")

    history = json.loads(HISTORY_FILE.read_text()) if HISTORY_FILE.exists() else []
    trends  = json.loads(TRENDS_FILE.read_text())  if TRENDS_FILE.exists()  else {}
    insights = json.loads(INSIGHTS_FILE.read_text()) if INSIGHTS_FILE.exists() else {}
    supplemental = json.loads(SUPP_FILE.read_text()) if SUPP_FILE.exists() else {}

    html = build_html(trends, insights, history, supplemental)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"OK Dashboard written -> {OUTPUT_FILE} ({len(html):,} chars)\n")

if __name__ == "__main__":
    main()
