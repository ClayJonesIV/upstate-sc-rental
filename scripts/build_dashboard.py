#!/usr/bin/env python3
"""
build_dashboard.py
Reads data/history.json, data/trends.json, data/insights.json
and writes a complete self-contained docs/index.html for GitHub Pages.
"""

import json
from datetime import datetime
from pathlib import Path

HISTORY_FILE = Path(__file__).parent.parent / "data" / "history.json"
TRENDS_FILE = Path(__file__).parent.parent / "data" / "trends.json"
INSIGHTS_FILE = Path(__file__).parent.parent / "data" / "insights.json"
SUPP_FILE = Path(__file__).parent.parent / "data" / "supplemental_latest.json"
OUTPUT_FILE = Path(__file__).parent.parent / "docs" / "index.html"

import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import MARKETS

GROUPS = {
    "headline": {
        "title": "Upstate Headline",
        "markets": list(MARKETS.keys()),
        "description": "High-level regional view across all tracked Upstate markets.",
    },
    "greenville": {
        "title": "Greenville",
        "markets": ["greenville"],
        "description": "Highest-confidence core market view with the cleanest direct source coverage.",
    },
    "spartanburg": {
        "title": "Spartanburg",
        "markets": ["spartanburg"],
        "description": "High-confidence market view with direct source coverage and steadier inventory depth.",
    },
    "other": {
        "title": "Other Markets",
        "markets": ["anderson", "simpsonville", "greer", "easley", "piedmont", "clemson", "seneca"],
        "description": "Directional view for Anderson, Simpsonville, Greer, Easley, Piedmont, Clemson, and Seneca.",
    },
}


def fmt_rent(value):
    if value is None:
        return "—"
    return f"${value:,.0f}"


def fmt_pct(value, show_sign=True):
    if value is None:
        return "—"
    sign = "+" if value > 0 and show_sign else ""
    return f"{sign}{value:.1f}%"


def fmt_days(value):
    if value is None:
        return "—"
    return f"{value:.0f}d"


def fmt_date(ts: str, fallback: str = "n/a") -> str:
    if not ts:
        return fallback
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return ts[:10] if len(ts) >= 10 else ts


def pct_class(value):
    if value is None:
        return ""
    return "up" if value > 0 else "down" if value < 0 else ""


def temp_color(temp):
    return {
        "hot": "#e07a6a",
        "warm": "#f4a235",
        "neutral": "#2f355d",
        "cool": "#5d729a",
        "cold": "#8b84b2",
    }.get(temp, "#2f355d")


def confidence_color(level: str) -> str:
    return {
        "high": "#2f355d",
        "solid": "#5d729a",
        "moderate": "#f4a235",
        "directional": "#d4845a",
        "low": "#e07a6a",
    }.get(level, "#2f355d")


def sample_gate(listings):
    count = int(round(listings)) if listings is not None else None
    if count is None:
        return {
            "count": None,
            "status": "unknown",
            "show_rent": True,
            "label": None,
            "confidence_floor": None,
            "confidence_cap": None,
        }
    if count < 10:
        return {
            "count": count,
            "status": "insufficient",
            "show_rent": False,
            "label": "Insufficient data",
            "confidence_floor": 40,
            "confidence_cap": None,
        }
    if count < 25:
        return {
            "count": count,
            "status": "low_sample",
            "show_rent": True,
            "label": f"Low sample (N={count})",
            "confidence_floor": None,
            "confidence_cap": 65,
        }
    return {
        "count": count,
        "status": "normal",
        "show_rent": True,
        "label": None,
        "confidence_floor": None,
        "confidence_cap": None,
    }


def pct_gap(primary, baseline):
    if primary is None or baseline is None or baseline == 0:
        return None
    return round(((primary - baseline) / baseline) * 100, 1)


def recent_history_market(history, market_key):
    latest = history[-1] if history else {"markets": {}}
    return latest.get("markets", {}).get(market_key, {})


def market_reliability(market_key, latest_market, trend_market, supp_market):
    latest_market = latest_market or {}
    trend_market = trend_market or {}
    supp_market = supp_market or {}
    gate = sample_gate(latest_market.get("totalListings"))

    rent_current = latest_market.get("averageRent")
    baseline = supp_market.get("zillow_avg")
    divergence_pct = pct_gap(rent_current, baseline)
    divergence_flag = divergence_pct is not None and abs(divergence_pct) > 20

    beds = supp_market.get("bedrooms", {})
    local_name = f"{MARKETS[market_key]['name']}, SC"
    fallback_invoked = False
    for bedroom in ["1", "2"]:
        detail = (beds.get(bedroom) or {}).get("source_detail")
        if detail and detail != local_name:
            fallback_invoked = True
    if supp_market.get("zillow_source") not in {None, "zip+city_blend"}:
        fallback_invoked = True
    if supp_market.get("zillow_avg") is None:
        fallback_invoked = True

    mom_data = (
        trend_market.get("aggregate", {})
        .get("averageRent", {})
        .get("changes", {})
        .get("mom", {})
    )

    return {
        "sample_gate": gate,
        "divergence_pct": divergence_pct,
        "divergence_flag": divergence_flag,
        "fallback_invoked": fallback_invoked,
        "zip_codes": MARKETS[market_key]["zips"],
        "mom_pct": mom_data.get("pct_change"),
        "mom_raw": mom_data.get("pct_change_raw"),
        "mom_reference": mom_data.get("reference_value"),
        "mom_anomaly": bool(mom_data.get("anomaly_flag")),
        "rent_current": rent_current,
    }


def market_confidence(market_key, latest_market, supp_market, trend_market=None):
    score = 35
    reasons = []
    reliability = market_reliability(market_key, latest_market, trend_market, supp_market)

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
        if detail == f"{MARKETS[market_key]['name']}, SC":
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
    if "Greenville-Anderson, SC" in fallback_details and market_key != "greenville":
        score -= 10
        reasons.append("metro fallback for support fields")

    notes = (MARKETS[market_key].get("notes") or "").lower()
    if "college market" in notes:
        score -= 10
        reasons.append("college seasonality")
    if "lake" in notes:
        score -= 8
        reasons.append("lake-market volatility")
    if (supp_market or {}).get("zillow_avg") is None:
        score -= 12
        reasons.append("missing blended Zillow average")

    if reliability["divergence_flag"]:
        score -= 10
        reasons.append("RentCast diverges from baseline cross-check")

    gate = reliability["sample_gate"]
    if gate["confidence_floor"] is not None:
        score = max(score, gate["confidence_floor"])
        reasons.append("minimum confidence floor for very thin sample")
    if gate["confidence_cap"] is not None:
        score = min(score, gate["confidence_cap"])
        reasons.append("confidence capped due to low sample size")

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

    return {
        "score": score,
        "level": level,
        "label": label,
        "reasons": reasons[:3],
        "reliability": reliability,
    }


def reliability_notes(reliability):
    notes = []
    gate = reliability["sample_gate"]
    if gate["status"] == "insufficient":
        notes.append("Average rent is suppressed because current listing depth is below 10.")
    elif gate["status"] == "low_sample":
        notes.append(f"Average rent is shown with caution because the current sample is only {gate['count']} listings.")
    if reliability["divergence_flag"]:
        notes.append("Zip-level RentCast average diverges significantly from the supplemental baseline and should be read as directional.")
    if reliability["mom_anomaly"]:
        notes.append("Latest monthly rent move falls outside the normal sanity band and should be verified before external use.")
    return notes


def data_inputs_html(reliability):
    divergence = (
        f"{reliability['divergence_pct']:+.1f}% versus supplemental baseline"
        if reliability["divergence_pct"] is not None
        else "n/a"
    )
    if reliability["mom_raw"] is not None:
        mom_line = (
            f"{reliability['mom_raw']:+.1f}% "
            f"(current {fmt_rent(reliability['rent_current'])}, prior {fmt_rent(reliability['mom_reference'])})"
        )
    else:
        mom_line = "n/a"
    return f"""
<details class="data-inputs">
  <summary>Data inputs</summary>
  <div class="data-inputs-body">
    <div><strong>RentCast listing count:</strong> {reliability['sample_gate']['count'] if reliability['sample_gate']['count'] is not None else 'n/a'}</div>
    <div><strong>Zip codes queried:</strong> {", ".join(reliability['zip_codes'])}</div>
    <div><strong>Fallback support invoked:</strong> {"Yes" if reliability['fallback_invoked'] else "No"}</div>
    <div><strong>Baseline cross-check:</strong> {divergence}</div>
    <div><strong>Latest MoM audit:</strong> {mom_line}</div>
  </div>
</details>
"""


def render_rent_value(value, reliability, compact=False):
    gate = reliability["sample_gate"]
    display = fmt_rent(value) if gate["show_rent"] else "Insufficient data"
    label = gate["label"]
    if not label:
        return display if not compact else f"<div>{display}</div>"
    css = "mini-flag" if compact else "metric-flag"
    if compact:
        return f"<div>{display}</div><div class='{css}'>{label}</div>"
    return f"{display}<div class='{css}'>{label}</div>"


def render_mom_value(value, reliability, compact=False):
    base = f"<span class='trend-item {pct_class(value)}'>MoM {fmt_pct(value)}</span>"
    if not reliability["mom_anomaly"]:
        return base
    note = "Unusual MoM movement — verify"
    css = "mini-flag" if compact else "metric-flag"
    return f"{base}<div class='{css}'>{note}</div>"


def group_confidence(group_keys, history, trends, supplemental):
    latest_history = history[-1] if history else {"markets": {}}
    weighted_scores = []
    for key in group_keys:
        latest_market = latest_history.get("markets", {}).get(key, {})
        trend_market = trends.get("markets", {}).get(key, {})
        supp_market = supplemental.get("markets", {}).get(key, {}) if supplemental else {}
        confidence = market_confidence(key, latest_market, supp_market, trend_market)
        weight = latest_market.get("totalListings") or 1
        weighted_scores.append((confidence["score"], weight))

    weighted_score = round(
        sum(score * weight for score, weight in weighted_scores) / sum(weight for _, weight in weighted_scores),
        1,
    ) if weighted_scores else 0

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


def aggregate_group_metrics(group_keys, history, trends):
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


def insight_paragraphs(text: str) -> str:
    headers = [
        "MARKET CONDITIONS",
        "IMPLICATIONS FOR CURRENT OWNERS",
        "VACANCY MARKETING STRATEGY",
        "RENEWAL PRICING STRATEGY",
        "UPSTATE SC MACRO VIEW",
        "OUTLOOK AND RISKS",
    ]
    html = (text or "").replace("**", "")
    for header in headers:
        html = html.replace(header, f'<h4 class="insight-header">{header}</h4>')
    blocks = []
    for chunk in html.split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.startswith("<h4"):
            blocks.append(chunk)
        else:
            blocks.append(f"<p>{chunk}</p>")
    return "\n".join(blocks)


def build_other_markets_table(group_keys, history, trends, supplemental):
    latest_history = history[-1] if history else {"markets": {}}
    rows = []
    for key in group_keys:
        market = latest_history.get("markets", {}).get(key, {})
        trend_market = trends.get("markets", {}).get(key, {})
        mom = trend_market.get("aggregate", {}).get("averageRent", {}).get("changes", {}).get("mom", {}).get("pct_change")
        temp = trend_market.get("market_conditions", {}).get("temperature_label", "n/a")
        supp_market = supplemental.get("markets", {}).get(key, {}) if supplemental else {}
        confidence = market_confidence(key, market, supp_market, trend_market)
        reliability = confidence["reliability"]
        conf_color = confidence_color(confidence["level"])
        note_lines = "".join(f"<div class='confidence-note'>{note}</div>" for note in reliability_notes(reliability))
        rows.append(
            f"<tr>"
            f"<td>{MARKETS[key]['name']}</td>"
            f"<td>{render_rent_value(market.get('averageRent'), reliability, compact=True)}</td>"
            f"<td>{render_mom_value(mom, reliability, compact=True)}</td>"
            f"<td>{temp}</td>"
            f"<td><span style='background:{conf_color}22;color:{conf_color};border:1px solid {conf_color}55;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;white-space:nowrap'>{confidence['score']:.0f} · {confidence['label']}</span>{note_lines}{data_inputs_html(reliability)}</td>"
            f"</tr>"
        )
    return "".join(rows)


def build_group_section(group_key, trends, insights, history, supplemental):
    group = GROUPS[group_key]
    metrics = aggregate_group_metrics(group["markets"], history, trends)
    confidence = group_confidence(group["markets"], history, trends, supplemental)
    color = "#2f355d" if group_key == "headline" else MARKETS[group["markets"][0]]["color"]
    tc = temp_color(metrics["temperature"])
    cc = confidence_color(confidence["level"])

    rent_value_html = fmt_rent(metrics["average_rent"])
    rent_mom_html = f"<span class='trend-item {pct_class(metrics['average_mom'])}'>MoM {fmt_pct(metrics['average_mom'])}</span>"
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
        latest_market = recent_history_market(history, market_key)
        trend_market = trends.get("markets", {}).get(market_key, {})
        supp_market = supplemental.get("markets", {}).get(market_key, {}) if supplemental else {}
        market_conf = market_confidence(market_key, latest_market, supp_market, trend_market)
        reliability = market_conf["reliability"]
        note_lines = "".join(f"<div>{note}</div>" for note in reliability_notes(reliability))
        note_block = f"<div class='confidence-stack'>{note_lines}</div>" if note_lines else ""
        rent_value_html = render_rent_value(metrics["average_rent"], reliability)
        rent_mom_html = render_mom_value(metrics["average_mom"], reliability)
        content = f"""
  <div class="source-block">
    <div class="source-label">Confidence Notes</div>
    <div class="source-text">
      <div>This score reflects listing depth, source specificity, and how much fallback logic was needed.</div>
      <div>Higher confidence means more direct local support and less metro-level estimation.</div>
      {note_block}
    </div>
    {data_inputs_html(reliability)}
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
      <div>Local sample depth, fallback support, and volatility matter more here than in the core markets.</div>
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
      <span class="temp-badge" title="Confidence combines listing depth, source specificity, fallback usage, and cross-check behavior." style="background:{cc}22;color:{cc};border:1px solid {cc}55">
        {confidence['score']:.0f} · {confidence['label']}
      </span>
    </div>
    <div class="market-label">{group['description']}</div>
  </div>

  <div class="metrics-row">
    <div class="metric-card" style="border-top-color:{color}">
      <div class="metric-label">Avg Rent</div>
      <div class="metric-val">{rent_value_html}</div>
      <div class="trend-row">{rent_mom_html}</div>
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


def build_html(trends, insights, history, supplemental):
    as_of = trends.get("as_of", "")
    as_of_display = datetime.strptime(as_of, "%Y-%m").strftime("%B %Y") if as_of else "—"
    generated = insights.get("generated_at", "")[:10]
    rentcast_fetched = history[-1].get("fetched_at", "") if history else ""
    rs = trends.get("regional_summary", {})

    avg_mom_values = [
        trends["markets"][key]["aggregate"]["averageRent"]["changes"]["mom"]["pct_change"]
        for key in MARKETS
        if trends["markets"][key]["aggregate"]["averageRent"]["changes"]["mom"]["pct_change"] is not None
    ]
    avg_mom_rent = round(sum(avg_mom_values) / len(avg_mom_values), 2) if avg_mom_values else None

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
.market-section{{background:var(--brand-surface);border:1px solid var(--brand-border);border-radius:14px;padding:28px;margin-bottom:28px;box-shadow:0 10px 30px rgba(45,46,48,.05)}}
.market-header{{margin-bottom:20px}}
.market-title-row{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:4px}}
.market-title-row h2{{font-size:20px;font-weight:700;font-family:'Montserrat',sans-serif}}
.market-label{{font-size:11px;color:var(--brand-muted);font-family:'Montserrat',sans-serif}}
.temp-badge{{padding:4px 12px;border-radius:20px;font-size:11px;font-weight:600;font-family:'Montserrat',sans-serif}}
.metrics-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:18px}}
.metric-card{{background:var(--brand-cream);border-radius:10px;padding:14px 16px;border-top:3px solid transparent}}
.metric-label{{font-size:10px;color:var(--brand-muted);text-transform:uppercase;letter-spacing:1px;font-family:'Montserrat',sans-serif;margin-bottom:4px}}
.metric-val{{font-size:24px;font-weight:800;color:var(--brand-charcoal);font-family:'Montserrat',sans-serif;margin-bottom:8px}}
.metric-flag{{margin-top:6px;font-size:11px;color:#b05b34;font-family:'Roboto',sans-serif;font-weight:500}}
.mini-flag{{margin-top:4px;font-size:10px;color:#b05b34;font-family:'Roboto',sans-serif}}
.confidence-note{{margin-top:8px;font-size:11px;color:#7a5c42;line-height:1.5}}
.confidence-stack{{margin-top:10px}}
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
.bedroom-table td{{padding:9px 12px;text-align:right;border-bottom:1px solid #eef1ed;vertical-align:top}}
.bedroom-table td:first-child{{text-align:left;font-weight:600;color:var(--brand-charcoal)}}
.insight-block{{background:#fbfcfa;border-radius:10px;padding:22px 24px;border-left:3px solid rgba(47,53,93,.28)}}
.insight-label{{font-size:10px;color:var(--brand-blue);letter-spacing:2px;text-transform:uppercase;font-family:'Montserrat',sans-serif;margin-bottom:14px;font-weight:700}}
.insight-header{{font-size:11px;color:var(--brand-blue);letter-spacing:1.5px;text-transform:uppercase;font-family:'Montserrat',sans-serif;font-weight:700;margin:20px 0 8px}}
.insight-block p{{font-size:14px;color:var(--brand-charcoal);line-height:1.75;margin-bottom:14px;font-family:'Roboto',sans-serif}}
.source-block{{background:#fbfcfa;border:1px solid var(--brand-border);border-radius:10px;padding:14px 16px;margin-bottom:18px}}
.source-label{{font-size:10px;color:var(--brand-orange);letter-spacing:2px;text-transform:uppercase;font-family:'Montserrat',sans-serif;margin-bottom:10px;font-weight:700}}
.source-text{{font-size:12px;color:var(--brand-charcoal);font-family:'Roboto',sans-serif;line-height:1.7}}
.data-inputs{{margin-top:12px}}
.data-inputs summary{{cursor:pointer;font-size:11px;color:var(--brand-blue);font-family:'Montserrat',sans-serif;font-weight:600}}
.data-inputs-body{{margin-top:8px;font-size:11px;color:var(--brand-charcoal);line-height:1.6}}
.legend-block{{background:#ffffff;border:1px solid var(--brand-border);border-left:4px solid var(--brand-orange);border-radius:10px;padding:14px 18px;margin-bottom:24px;font-size:13px;color:var(--brand-charcoal);font-family:'Roboto',sans-serif;line-height:1.7}}
.legend-title{{font-size:10px;color:var(--brand-orange);letter-spacing:2px;text-transform:uppercase;font-family:'Montserrat',sans-serif;font-weight:700;margin-bottom:8px}}
.data-note{{background:#ffffff;border:1px solid var(--brand-border);border-left:4px solid var(--brand-blue);border-radius:8px;padding:14px 18px;margin-bottom:24px;font-size:13px;color:var(--brand-charcoal);font-family:'Roboto',sans-serif;line-height:1.6}}
.source-refresh{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-bottom:16px}}
.source-refresh-card{{background:#ffffff;border:1px solid var(--brand-border);border-radius:10px;padding:14px 16px}}
.source-refresh-name{{font-size:10px;color:var(--brand-muted);text-transform:uppercase;letter-spacing:1px;font-family:'Montserrat',sans-serif;margin-bottom:6px}}
.source-refresh-date{{font-size:16px;color:var(--brand-charcoal);font-family:'Montserrat',sans-serif;font-weight:700}}
.source-refresh-note{{font-size:12px;color:var(--brand-muted);font-family:'Roboto',sans-serif;margin-top:4px}}
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
    <div>Confidence scores combine listing depth, source specificity, fallback usage, and baseline cross-check behavior.</div>
    <div>Lower sample sizes trigger visible cautions, while unusual monthly moves are flagged for review rather than hidden.</div>
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
    trends = json.loads(TRENDS_FILE.read_text()) if TRENDS_FILE.exists() else {}
    insights = json.loads(INSIGHTS_FILE.read_text()) if INSIGHTS_FILE.exists() else {}
    supplemental = json.loads(SUPP_FILE.read_text()) if SUPP_FILE.exists() else {}

    html = build_html(trends, insights, history, supplemental)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"OK Dashboard written -> {OUTPUT_FILE} ({len(html):,} chars)\n")


if __name__ == "__main__":
    main()
