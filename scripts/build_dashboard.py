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

GROUPS = {
    "headline": {
        "title": "Upstate Headline",
        "markets": list(MARKETS.keys()),
        "description": "High-level regional view across all tracked Upstate markets.",
        "show_bedrooms": False,
    },
    "greenville": {
        "title": "Greenville",
        "markets": ["greenville"],
        "description": "Highest-confidence core market view with the cleanest direct source coverage.",
        "show_bedrooms": True,
    },
    "spartanburg": {
        "title": "Spartanburg",
        "markets": ["spartanburg"],
        "description": "High-confidence market view with direct source coverage and steadier inventory depth.",
        "show_bedrooms": True,
    },
    "other": {
        "title": "Other Markets",
        "markets": ["anderson", "simpsonville", "greer", "easley", "piedmont", "clemson", "seneca"],
        "description": "Directional view for Anderson, Simpsonville, Greer, Easley, Piedmont, Clemson, and Seneca.",
        "show_bedrooms": False,
    },
}

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
        "neutral": "#2f355d", "cool": "#5d729a", "cold": "#8b84b2"
    }.get(temp, "#2f355d")


def confidence_color(level: str) -> str:
    return {
        "high": "#2f355d",
        "solid": "#5d729a",
        "moderate": "#f4a235",
        "directional": "#d4845a",
        "low": "#e07a6a",
    }.get(level, "#2f355d")


def fmt_date(ts: str, fallback: str = "n/a") -> str:
    if not ts:
        return fallback
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return ts[:10] if len(ts) >= 10 else ts


def market_confidence(mkt_key: str, latest_market: dict | None, supp_market: dict | None) -> dict:
    score = 35
    reasons = []

    listings = (latest_market or {}).get("totalListings")
    if listings is not None:
        if listings >= 100:
            score += 22
            reasons.append("deep listing volume")
        elif listings >= 50:
            score += 16
            reasons.append("good listing volume")
        elif listings >= 25:
            score += 8
            reasons.append("moderate listing volume")
        else:
            reasons.append("thin listing volume")

    z_source = (supp_market or {}).get("zillow_source")
    if z_source == "zip+city_blend":
        score += 14
        reasons.append("zip and city Zillow support")
    elif z_source == "city":
        score += 6
        reasons.append("city-only Zillow support")
    else:
        score -= 6
        reasons.append("limited Zillow support")

    beds = (supp_market or {}).get("bedrooms", {})
    for bedroom in ["1", "2"]:
        detail = (beds.get(bedroom) or {}).get("source_detail") or ""
        if detail == f"{MARKETS[mkt_key]['name']}, SC":
            score += 8
        elif detail:
            score += 2
    for bedroom in ["3", "4"]:
        if (beds.get(bedroom) or {}).get("source") == "zillow_derived":
            score += 3

    fallback_details = {
        (beds.get("1") or {}).get("source_detail"),
        (beds.get("2") or {}).get("source_detail"),
    }
    if "Greenville-Anderson, SC" in fallback_details and mkt_key != "greenville":
        score -= 10
        reasons.append("metro fallback for 1BR/2BR")

    notes = (MARKETS[mkt_key].get("notes") or "").lower()
    if "college market" in notes:
        score -= 10
        reasons.append("college seasonality")
    if "lake" in notes:
        score -= 8
        reasons.append("lake-market volatility")
    if (supp_market or {}).get("zillow_avg") is None:
        score -= 12
        reasons.append("missing blended Zillow average")

    score = max(20, min(95, score))
    if score >= 85:
        level = "high"
        label = "High Confidence"
    elif score >= 70:
        level = "solid"
        label = "Solid Confidence"
    elif score >= 55:
        level = "moderate"
        label = "Moderate Confidence"
    elif score >= 40:
        level = "directional"
        label = "Directional"
    else:
        level = "low"
        label = "Low Confidence"

    return {"score": score, "level": level, "label": label, "reasons": reasons[:3]}


def group_confidence(group_keys: list[str], history: list, supplemental: dict) -> dict:
    latest_history = history[-1] if history else {"markets": {}}
    weighted_scores = []
    for key in group_keys:
        latest_market = latest_history.get("markets", {}).get(key, {})
        supp_market = supplemental.get("markets", {}).get(key, {}) if supplemental else {}
        confidence = market_confidence(key, latest_market, supp_market)
        weight = latest_market.get("totalListings") or 1
        weighted_scores.append((confidence["score"], weight))

    weighted_score = round(sum(score * weight for score, weight in weighted_scores) / sum(weight for _, weight in weighted_scores), 1) if weighted_scores else 0
    if weighted_score >= 85:
        level = "high"
        label = "High Confidence"
    elif weighted_score >= 70:
        level = "solid"
        label = "Solid Confidence"
    elif weighted_score >= 55:
        level = "moderate"
        label = "Moderate Confidence"
    elif weighted_score >= 40:
        level = "directional"
        label = "Directional"
    else:
        level = "low"
        label = "Low Confidence"

    return {"score": weighted_score, "level": level, "label": label}


def aggregate_group_metrics(group_keys: list[str], history: list, trends: dict) -> dict:
    latest_history = history[-1] if history else {"markets": {}}
    rent_vals, dom_vals, listing_vals = [], [], []
    weighted_rent_mom = []
    weighted_dom_mom = []
    temps = []
    for key in group_keys:
        hist_market = latest_history.get("markets", {}).get(key)
        trend_market = trends.get("markets", {}).get(key, {})
        listings_weight = trend_market.get("aggregate", {}).get("totalListings", {}).get("current")
        if hist_market:
            if hist_market.get("averageRent") is not None:
                rent_vals.append((hist_market["averageRent"], listings_weight or 1))
            if hist_market.get("averageDaysOnMarket") is not None:
                dom_vals.append((hist_market["averageDaysOnMarket"], listings_weight or 1))
            if hist_market.get("totalListings") is not None:
                listing_vals.append(hist_market["totalListings"])
        mom = trend_market.get("aggregate", {}).get("averageRent", {}).get("changes", {}).get("mom", {}).get("pct_change")
        dom_mom = trend_market.get("aggregate", {}).get("averageDaysOnMarket", {}).get("changes", {}).get("mom", {}).get("pct_change")
        if mom is not None:
            weighted_rent_mom.append((mom, listings_weight or 1))
        if dom_mom is not None:
            weighted_dom_mom.append((dom_mom, listings_weight or 1))
        temp = trend_market.get("market_conditions", {}).get("temperature")
        if temp:
            temps.append(temp)

    temp_order = {"hot": 2, "warm": 1, "neutral": 0, "cool": -1, "cold": -2}
    avg_temp = round(sum(temp_order[t] for t in temps) / len(temps), 2) if temps else 0
    if avg_temp >= 1.5:
        temp = "hot"
        temp_label = "Landlord-Leaning"
    elif avg_temp >= 0.5:
        temp = "warm"
        temp_label = "Slightly Landlord-Favored"
    elif avg_temp > -0.5:
        temp = "neutral"
        temp_label = "Mixed but Balanced"
    elif avg_temp > -1.5:
        temp = "cool"
        temp_label = "Softer Leasing Conditions"
    else:
        temp = "cold"
        temp_label = "Renter-Leaning"

    return {
        "average_rent": round(sum(value * weight for value, weight in rent_vals) / sum(weight for _, weight in rent_vals), 2) if rent_vals else None,
        "average_dom": round(sum(value * weight for value, weight in dom_vals) / sum(weight for _, weight in dom_vals), 2) if dom_vals else None,
        "total_listings": round(sum(listing_vals), 2) if listing_vals else None,
        "average_mom": round(sum(value * weight for value, weight in weighted_rent_mom) / sum(weight for _, weight in weighted_rent_mom), 2) if weighted_rent_mom else None,
        "average_dom_mom": round(sum(value * weight for value, weight in weighted_dom_mom) / sum(weight for _, weight in weighted_dom_mom), 2) if weighted_dom_mom else None,
        "temperature": temp,
        "temperature_label": temp_label,
    }


def build_other_markets_table(group_keys: list[str], history: list, trends: dict, supplemental: dict) -> str:
    latest_history = history[-1] if history else {"markets": {}}
    rows = []
    for key in group_keys:
        market = latest_history.get("markets", {}).get(key, {})
        trend_market = trends.get("markets", {}).get(key, {})
        mom = trend_market.get("aggregate", {}).get("averageRent", {}).get("changes", {}).get("mom", {}).get("pct_change")
        temp = trend_market.get("market_conditions", {}).get("temperature_label", "n/a")
        supp_market = supplemental.get("markets", {}).get(key, {}) if supplemental else {}
        confidence = market_confidence(key, market, supp_market)
        conf_color = confidence_color(confidence["level"])
        rows.append(
            f"<tr>"
            f"<td>{MARKETS[key]['name']}</td>"
            f"<td>{fmt_rent(market.get('averageRent'))}</td>"
            f"<td class='{pct_class(mom)}'>{fmt_pct(mom)}</td>"
            f"<td>{temp}</td>"
            f"<td><span style='background:{conf_color}22;color:{conf_color};border:1px solid {conf_color}55;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;white-space:nowrap'>{confidence['score']:.0f} · {confidence['label']}</span></td>"
            f"</tr>"
        )
    return "".join(rows)


def build_group_section(group_key: str, trends: dict, insights: dict, history: list, supplemental: dict) -> str:
    group = GROUPS[group_key]
    metrics = aggregate_group_metrics(group["markets"], history, trends)
    confidence = group_confidence(group["markets"], history, supplemental)
    color = "#2f355d" if group_key == "headline" else MARKETS[group["markets"][0]]["color"]
    tc = temp_color(metrics["temperature"])
    cc = confidence_color(confidence["level"])

    content = ""
    if group_key == "headline":
        content = f"""
  <div class="insight-block">
    <div class="insight-label">Regional Market Analysis</div>
    {insight_paragraphs(insights.get('regional', 'Analysis not available.'))}
  </div>
"""
    elif group_key in {"greenville", "spartanburg"}:
        market_key = group["markets"][0]
        content = f"""
  <div class="source-block">
    <div class="source-label">Confidence Notes</div>
    <div class="source-text">
      <div>This score reflects listing depth, source specificity, and how much fallback logic was needed.</div>
      <div>Higher confidence means more direct local support and less metro-level estimation.</div>
    </div>
  </div>
  <div class="insight-block">
    <div class="insight-label">Market Analysis</div>
    {insight_paragraphs(insights.get('markets', {}).get(market_key, 'Analysis not available.'))}
  </div>
"""
    else:
        content = f"""
  <div class="source-block">
    <div class="source-label">Confidence Note</div>
    <div class="source-text">
      <div>These markets are best read as directional rather than highly precise.</div>
      <div>Examples included: Anderson, Simpsonville, Greer, Easley, Piedmont, Clemson, and Seneca.</div>
      <div>The confidence score helps separate stronger ring-market signals from thinner special-case markets.</div>
      <div>Local sample depth and market volatility matter more here than in the core markets.</div>
    </div>
  </div>
  <div class="bedroom-table-wrap">
    <table class="bedroom-table">
      <thead><tr><th>Market</th><th>Avg Rent</th><th>MoM</th><th>Temp</th><th>Confidence</th></tr></thead>
      <tbody>{build_other_markets_table(group['markets'], history, trends, supplemental)}</tbody>
    </table>
  </div>
"""

    return f"""
<div class="market-section" id="group-{group_key}">
  <div class="market-header" style="border-left: 4px solid {color}">
    <div class="market-title-row">
      <h2 style="color:{color}">{group['title']}</h2>
      <span class="temp-badge" style="background:{tc}22;color:{tc};border:1px solid {tc}55">
        {metrics['temperature_label']}
      </span>
      <span class="temp-badge" title="Confidence combines listing depth, source specificity, and how much fallback estimation was needed." style="background:{cc}22;color:{cc};border:1px solid {cc}55">
        {confidence['score']:.0f} · {confidence['label']}
      </span>
    </div>
    <div class="market-label">{group['description']}</div>
  </div>

  <div class="metrics-row">
    <div class="metric-card" style="border-top-color:{color}">
      <div class="metric-label">Avg Rent</div>
      <div class="metric-val">{fmt_rent(metrics['average_rent'])}</div>
      <div class="trend-row">
        <span class="trend-item {pct_class(metrics['average_mom'])}">MoM {fmt_pct(metrics['average_mom'])}</span>
      </div>
    </div>
    <div class="metric-card" style="border-top-color:{color}">
      <div class="metric-label">Days on Market</div>
      <div class="metric-val">{fmt_days(metrics['average_dom'])}</div>
      <div class="trend-row">
        {f'<span class="trend-item {pct_class(-metrics["average_dom_mom"]) if metrics["average_dom_mom"] is not None else ""}">MoM {fmt_pct(metrics["average_dom_mom"])}</span>' if group_key != "other" else ''}
        <span class="trend-note">(lower is better)</span>
      </div>
    </div>
    <div class="metric-card" style="border-top-color:{color}">
      <div class="metric-label">Active Listings</div>
      <div class="metric-val">{f"{metrics['total_listings']:,.0f}" if metrics['total_listings'] is not None else '—'}</div>
      <div class="trend-row"><span class="trend-note">(tier-level summary)</span></div>
    </div>
  </div>
  {content}
</div>
"""

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
    <div class="insight-label">Market Analysis</div>
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

    headline_section = build_group_section("headline", trends, insights, history, supplemental)
    greenville_section = build_group_section("greenville", trends, insights, history, supplemental)
    spartanburg_section = build_group_section("spartanburg", trends, insights, history, supplemental)
    other_section = build_group_section("other", trends, insights, history, supplemental)

    nav_links = " · ".join([
        '<a href="#group-headline">Upstate</a>',
        '<a href="#group-greenville">Greenville</a>',
        '<a href="#group-spartanburg">Spartanburg</a>',
        '<a href="#group-other">Other Markets</a>',
    ])

    hottest = MARKETS.get(rs.get("hottest_market", ""), {}).get("name", "—")
    softest = MARKETS.get(rs.get("softest_market", ""), {}).get("name", "—")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Upstate SC Rental Market — {as_of_display}</title>
<style>
:root{{
  --brand-blue:#2f355d;
  --brand-blue-deep:#232845;
  --brand-blue-soft:#46507d;
  --brand-orange:#fd5315;
  --brand-charcoal:#2d2e30;
  --brand-charcoal-deep:#1e1e1e;
  --brand-cream:#f7f7f3;
  --brand-surface:#ffffff;
  --brand-border:#d9ded7;
  --brand-muted:#6b716c;
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{font-size:15px;scroll-behavior:smooth}}
body{{background:linear-gradient(180deg,#f7f7f3,#eef3eb);color:var(--brand-charcoal);font-family:'Roboto',sans-serif;line-height:1.6}}
a{{color:var(--brand-blue);text-decoration:none}}
a:hover{{text-decoration:underline}}

.site-header{{background:linear-gradient(135deg,var(--brand-blue),var(--brand-blue-deep));border-bottom:4px solid var(--brand-blue-soft);padding:32px 40px 24px}}
.eyebrow{{font-size:10px;color:#ffffff;letter-spacing:2.5px;text-transform:uppercase;font-family:'Montserrat',sans-serif;font-weight:700;margin-bottom:8px}}
h1{{font-size:32px;font-weight:700;color:#fff;margin-bottom:6px;font-family:'Montserrat',sans-serif}}
h1 em{{color:#d7e4f2;font-style:normal}}
.subtitle{{font-size:11px;color:#d1d6d1;font-family:'Montserrat',sans-serif;margin-bottom:20px}}

.nav-bar{{font-size:12px;color:var(--brand-muted);font-family:'Montserrat',sans-serif;padding:12px 40px;background:#ffffff;border-bottom:1px solid var(--brand-border)}}
.nav-bar a{{color:var(--brand-blue);margin-right:4px}}

.hero-stats{{display:flex;flex-wrap:wrap;gap:12px;margin-top:20px}}
.hero-stat{{background:var(--brand-cream);border-radius:10px;padding:12px 18px;min-width:110px;text-align:center;border:1px solid var(--brand-border);box-shadow:0 8px 18px rgba(45,46,48,.08)}}
.hs-label{{font-size:10px;color:var(--brand-muted);text-transform:uppercase;letter-spacing:1px;font-family:'Montserrat',sans-serif}}
.hs-val{{font-size:20px;font-weight:800;margin-top:3px;font-family:'Montserrat',sans-serif}}

.main{{max-width:1100px;margin:0 auto;padding:32px 40px 60px}}

.section-header{{font-size:11px;color:var(--brand-blue);letter-spacing:2px;text-transform:uppercase;font-family:'Montserrat',sans-serif;font-weight:700;margin:40px 0 20px;padding-bottom:8px;border-bottom:1px solid var(--brand-border)}}

.regional-block{{background:var(--brand-surface);border:1px solid var(--brand-border);border-radius:14px;padding:28px;margin-bottom:36px}}
.regional-title{{font-size:16px;color:var(--brand-charcoal);margin-bottom:16px;font-family:'Montserrat',sans-serif}}
.insight-header{{font-size:11px;color:var(--brand-blue);letter-spacing:1.5px;text-transform:uppercase;font-family:'Montserrat',sans-serif;font-weight:700;margin:20px 0 8px}}
.insight-block p{{font-size:14px;color:var(--brand-charcoal);line-height:1.75;margin-bottom:14px;font-family:'Roboto',sans-serif}}

.market-section{{background:var(--brand-surface);border:1px solid var(--brand-border);border-radius:14px;padding:28px;margin-bottom:28px;box-shadow:0 10px 30px rgba(45,46,48,.05)}}
.market-header{{margin-bottom:20px}}
.market-title-row{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:4px}}
.market-title-row h2{{font-size:20px;font-weight:700;font-family:'Montserrat',sans-serif}}
.market-label{{font-size:11px;color:var(--brand-muted);font-family:'Montserrat',sans-serif}}

.temp-badge{{padding:4px 12px;border-radius:20px;font-size:11px;font-weight:600;font-family:'Montserrat',sans-serif}}
.tier-badge{{font-size:9px;padding:2px 8px;border-radius:8px;font-family:'Montserrat',sans-serif;letter-spacing:.5px;vertical-align:middle}}
.tier-full{{background:rgba(47,53,93,.12);color:var(--brand-blue);border:1px solid rgba(47,53,93,.25)}}
.tier-snap{{background:rgba(253,83,21,.10);color:var(--brand-orange);border:1px solid rgba(253,83,21,.25)}}

.metrics-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:18px}}
.metric-card{{background:var(--brand-cream);border-radius:10px;padding:14px 16px;border-top:3px solid transparent}}
.metric-label{{font-size:10px;color:var(--brand-muted);text-transform:uppercase;letter-spacing:1px;font-family:'Montserrat',sans-serif;margin-bottom:4px}}
.metric-val{{font-size:24px;font-weight:800;color:var(--brand-charcoal);font-family:'Montserrat',sans-serif;margin-bottom:8px}}
.trend-row{{display:flex;flex-wrap:wrap;gap:6px;align-items:center}}
.trend-item{{font-size:11px;font-family:'Montserrat',sans-serif;padding:2px 7px;border-radius:6px;font-weight:600}}
.trend-item.up{{background:rgba(47,53,93,.14);color:var(--brand-blue)}}
.trend-item.down{{background:rgba(253,83,21,.12);color:var(--brand-orange)}}
.trend-item:not(.up):not(.down){{background:#eef1ed;color:var(--brand-muted)}}
.trend-note{{font-size:10px;color:var(--brand-muted);font-family:'Roboto',sans-serif;font-style:italic}}

.bedroom-table-wrap{{overflow-x:auto;margin-bottom:20px}}
.bedroom-table{{width:100%;border-collapse:collapse;font-size:13px;font-family:'Roboto',sans-serif}}
.bedroom-table th{{padding:8px 12px;text-align:right;color:var(--brand-muted);font-weight:600;font-size:10px;letter-spacing:.5px;text-transform:uppercase;border-bottom:1px solid var(--brand-border)}}
.bedroom-table th:first-child{{text-align:left}}
.bedroom-table td{{padding:9px 12px;text-align:right;border-bottom:1px solid #eef1ed}}
.bedroom-table td:first-child{{text-align:left;font-weight:600;color:var(--brand-charcoal)}}
.bedroom-table td.up{{color:var(--brand-blue);font-weight:700}}
.bedroom-table td.down{{color:var(--brand-orange);font-weight:700}}

.insight-block{{background:#fbfcfa;border-radius:10px;padding:22px 24px;border-left:3px solid rgba(47,53,93,.28)}}
.insight-label{{font-size:10px;color:var(--brand-blue);letter-spacing:2px;text-transform:uppercase;font-family:'Montserrat',sans-serif;margin-bottom:14px;font-weight:700}}
.source-block{{background:#fbfcfa;border:1px solid var(--brand-border);border-radius:10px;padding:14px 16px;margin-bottom:18px}}
.source-label{{font-size:10px;color:var(--brand-orange);letter-spacing:2px;text-transform:uppercase;font-family:'Montserrat',sans-serif;margin-bottom:10px;font-weight:700}}
.source-text{{font-size:12px;color:var(--brand-charcoal);font-family:'Roboto',sans-serif;line-height:1.7}}
.source-refresh{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-bottom:16px}}
.source-refresh-card{{background:#ffffff;border:1px solid var(--brand-border);border-radius:10px;padding:14px 16px}}
.source-refresh-name{{font-size:10px;color:var(--brand-muted);text-transform:uppercase;letter-spacing:1px;font-family:'Montserrat',sans-serif;margin-bottom:6px}}
.source-refresh-date{{font-size:16px;color:var(--brand-charcoal);font-family:'Montserrat',sans-serif;font-weight:700}}
.source-refresh-note{{font-size:12px;color:var(--brand-muted);font-family:'Roboto',sans-serif;margin-top:4px}}

.legend-block{{background:#ffffff;border:1px solid var(--brand-border);border-left:4px solid var(--brand-orange);border-radius:10px;padding:14px 18px;margin-bottom:24px;font-size:13px;color:var(--brand-charcoal);font-family:'Roboto',sans-serif;line-height:1.7}}
.legend-title{{font-size:10px;color:var(--brand-orange);letter-spacing:2px;text-transform:uppercase;font-family:'Montserrat',sans-serif;font-weight:700;margin-bottom:8px}}
.data-note{{background:#ffffff;border:1px solid var(--brand-border);border-left:4px solid var(--brand-blue);border-radius:8px;padding:14px 18px;margin-bottom:24px;font-size:13px;color:var(--brand-charcoal);font-family:'Roboto',sans-serif;line-height:1.6}}

.footer{{text-align:center;font-size:11px;color:var(--brand-muted);font-family:'Montserrat',sans-serif;margin-top:60px;padding-top:20px;border-top:1px solid var(--brand-border)}}

@media(max-width:600px){{
  .site-header,.main,.nav-bar{{padding-left:20px;padding-right:20px}}
  .metrics-row{{grid-template-columns:1fr 1fr}}
}}
</style>
</head>
<body>

<div class="site-header">
  <div class="eyebrow">Jones Assurance Property Management · Upstate South Carolina</div>
  <h1>Rental Market <em>Intelligence</em></h1>
  <p class="subtitle">Auto-refreshed monthly · Last updated {generated}</p>
  <div class="hero-stats">
    <div class="hero-stat">
      <div class="hs-label">Report Period</div>
      <div class="hs-val" style="color:#2f355d;font-size:15px">{as_of_display}</div>
    </div>
    <div class="hero-stat">
      <div class="hs-label">Avg MoM Rent</div>
      <div class="hs-val" style="color:{'#2f355d' if (avg_mom_rent or 0) >= 0 else '#e07a6a'}">{fmt_pct(avg_mom_rent)}</div>
    </div>
    <div class="hero-stat">
      <div class="hs-label">Hottest Market</div>
      <div class="hs-val" style="color:#f4a235;font-size:15px">{hottest}</div>
    </div>
    <div class="hero-stat">
      <div class="hs-label">Softest Market</div>
      <div class="hs-val" style="color:#5d729a;font-size:15px">{softest}</div>
    </div>
  </div>
</div>

<div class="nav-bar">Jump to: {nav_links}</div>

<div class="main">
  <div class="legend-block">
    <div style="margin-bottom:14px">
      <p style="margin:0 0 10px 0">This dashboard combines core market metrics to give a practical view of leasing conditions across the Upstate.</p>
      <p style="margin:0">The confidence framework helps show which markets are backed by stronger local data and which ones should be read more cautiously as directional signals.</p>
    </div>
    <div class="legend-title">Confidence Guide</div>
    <div>Confidence scores combine listing depth, source specificity, and how much fallback estimation was needed.</div>
    <div>Higher scores mean stronger local support. Lower scores should be read as directional rather than precise.</div>
  </div>

  <div class="section-header">Tiered Market View</div>
  {headline_section}
  {greenville_section}
  {spartanburg_section}
  {other_section}

  <div class="data-note">
    <strong>Jones Assurance PM Market View:</strong> Market data pulled monthly from
    <strong>RentCast API</strong> (rentcast.io) covering 18 zip codes across 10 Upstate SC markets.
    Data reflects active rental listings only.
    <strong>Not financial advice.</strong>
  </div>

  <div class="source-refresh">
    <div class="source-refresh-card">
      <div class="source-refresh-name">RentCast Refresh</div>
      <div class="source-refresh-date">{fmt_date(rentcast_fetched)}</div>
      <div class="source-refresh-note">Latest live RentCast pull used for core market metrics</div>
    </div>
    <div class="source-refresh-card">
      <div class="source-refresh-name">Report Refresh</div>
      <div class="source-refresh-date">{generated or 'n/a'}</div>
      <div class="source-refresh-note">Latest narrative and dashboard update date</div>
    </div>
  </div>

  <div class="footer">
    Jones Assurance Property Management · Rental Market Intelligence · Data: RentCast API ·
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
