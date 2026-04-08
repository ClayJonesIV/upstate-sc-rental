#!/usr/bin/env python3
"""
generate_insights.py
Calls Claude API to produce deep narrative market analysis:
  - Per-market: conditions, implications for owners, vacancy marketing strategy,
    renewal pricing recommendation (raise/hold/and by how much)
  - Regional summary: Upstate SC macro view + cross-market investment thesis
Writes output to data/insights.json.
"""

import os
import json
from pathlib import Path
from datetime import datetime
import anthropic

TRENDS_FILE   = Path(__file__).parent.parent / "data" / "trends.json"
HISTORY_FILE  = Path(__file__).parent.parent / "data" / "history.json"
INSIGHTS_FILE = Path(__file__).parent.parent / "data" / "insights.json"
SUPP_FILE     = Path(__file__).parent.parent / "data" / "supplemental_latest.json"

sys_path = str(Path(__file__).parent)
import sys
sys.path.insert(0, sys_path)
from config import MARKETS

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ─── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior real estate market analyst specializing in the Upstate South Carolina rental market.
You write reports for rental property owners who want credible guidance without heavy jargon.
Your tone should establish expertise quickly, then explain the takeaway in plain English.
Be conservative on pricing recommendations because most owners prefer lower vacancy over squeezing for top rent.
Use only the provided data and source notes. Do not invent outside facts.
Do not use bullet points. Write in paragraphs only.
Do not use quarter-over-quarter or year-over-year data in any analysis or recommendation."""


def sanitize_market_text(mkt_key: str, text: str) -> str:
    if not text:
        return text
    cleaned = text
    if mkt_key == "greenville":
        cleaned = cleaned.replace("Greenville-Anderson-Mauldin rental market", "Greenville rental market")
        cleaned = cleaned.replace("Greenville-Anderson-Mauldin market", "Greenville market")
    return cleaned


def sanitize_regional_text(text: str) -> str:
    if not text:
        return text
    cleaned = text
    cleaned = cleaned.replace("Liberty and Seneca", "some smaller outlying markets and Seneca")
    cleaned = cleaned.replace("Seneca and Liberty", "Seneca and some smaller outlying markets")
    cleaned = cleaned.replace("like Liberty and Seneca", "like some smaller outlying markets and Seneca")
    cleaned = cleaned.replace("Liberty's", "one smaller outlying market's")
    cleaned = cleaned.replace(" Liberty ", " a smaller outlying market ")
    cleaned = cleaned.replace(" and Liberty", "")
    cleaned = cleaned.replace("Liberty, ", "")
    return cleaned


def recent_series(history: list, mkt_key: str, metric: str, months: int = 4) -> list[dict]:
    series = []
    for record in history[-months:]:
        market = record.get("markets", {}).get(mkt_key) or {}
        series.append({"month": record.get("month"), "value": market.get(metric)})
    return series


def source_context(supplemental: dict | None, history: list) -> str:
    rentcast_date = history[-1].get("fetched_at", "")[:10] if history else "unknown"
    supp_date = supplemental.get("fetched_at", "")[:10] if supplemental else "unknown"
    return (
        f"Recent sources available for citation:\n"
        f"- RentCast market data: {rentcast_date}\n"
        f"- Apartment List and Zillow supplemental data: {supp_date}\n"
        f"When writing Outlook and Risks, cite the available sources in plain text like "
        f"'(Sources: RentCast {rentcast_date}; Apartment List/Zillow {supp_date})'."
    )

def market_prompt(mkt_key: str, mkt_cfg: dict, mkt_trends: dict, month: str, history: list, supplemental: dict | None) -> str:
    agg = mkt_trends["aggregate"]
    cond = mkt_trends["market_conditions"]
    beds = mkt_trends["bedrooms"]

    rent_cur  = agg["averageRent"]["current"]
    rent_mom  = agg["averageRent"]["changes"]["mom"]["pct_change"]
    dom_cur   = agg["averageDaysOnMarket"]["current"]
    dom_mom   = agg["averageDaysOnMarket"]["changes"]["mom"]["pct_change"]
    inv_cur   = agg["totalListings"]["current"]
    inv_mom   = agg["totalListings"]["changes"]["mom"]["pct_change"]
    vacancy_proxy = recent_series(history, mkt_key, "averageDaysOnMarket", months=4)
    listing_proxy = recent_series(history, mkt_key, "totalListings", months=4)
    supp_market = supplemental.get("markets", {}).get(mkt_key, {}) if supplemental else {}

    bed_summary = ""
    for b in ["1", "2", "3", "4"]:
        bd = beds.get(b, {})
        r = bd.get("averageRent", {}).get("current")
        d = bd.get("averageDaysOnMarket", {}).get("current")
        if r:
            source_detail = supp_market.get("bedrooms", {}).get(b, {}).get("source_detail")
            source_note = f" ({source_detail})" if source_detail else ""
            bed_summary += f"\n  {b}BR: avg rent ${r:,.0f}{source_note}" + (f", DOM {d:.0f}d" if d else "")

    notes = mkt_cfg.get("notes", "")
    notes_line = f"\nMarket notes: {notes}" if notes else ""

    return f"""Write a deep narrative analysis for the {mkt_cfg['name']} rental market for {month}.
{notes_line}

CURRENT DATA:
- Use the exact market name "{mkt_cfg['name']}" when referring to this market.
- Do not rename it to a metro, county, or MSA label.
- Context label for orientation only: {mkt_cfg['label']}
- Market temperature: {cond['temperature_label']} (score: {cond['score']})
- Average rent: {f'${rent_cur:,.0f}' if rent_cur else 'N/A'}
  - MoM: {f'{rent_mom:+.1f}%' if rent_mom is not None else 'N/A'}
- Days on market: {f'{dom_cur:.0f}' if dom_cur else 'N/A'} days
  - MoM: {f'{dom_mom:+.1f}%' if dom_mom is not None else 'N/A'}
- Active listings: {f'{inv_cur:,.0f}' if inv_cur else 'N/A'}
  - MoM: {f'{inv_mom:+.1f}%' if inv_mom is not None else 'N/A'}
- By bedroom:{bed_summary}
- Recent 4-month days-on-market series: {vacancy_proxy}
- Recent 4-month active listings series: {listing_proxy}

SOURCE NOTES:
{source_context(supplemental, history)}

Write exactly FOUR paragraphs with these headers on their own line before each:

MARKET CONDITIONS
Open with a short sentence that sounds expert, then explain the takeaway in plain English.
Describe what the latest month and recent short trend reveal about supply, demand, and pricing pressure.
Do not mention quarter-over-quarter or year-over-year data.

IMPLICATIONS FOR CURRENT OWNERS
Explain what this means for a typical owner in practical, non-jargon terms.
Should they feel confident, cautious, or proactive? Keep the advice conservative.

VACANCY MARKETING STRATEGY
Focus only on pricing relative to comps and vacancy risk.
Say whether pricing should be aggressive, at market, or slightly below stronger comps to reduce vacancy.
Use the recent 3-month vacancy proxy trend from days on market and listings when giving the recommendation.
Be conservative: when uncertain, favor lower vacancy over pushing rent.

RENEWAL PRICING STRATEGY
Keep this high-level and conservative.
Say whether owners should prioritize holding rent, making only modest increases, or pushing increases when the latest market clearly supports it.
Avoid detailed pricing math and avoid aggressive advice."""

def regional_prompt(trends: dict, month: str, history: list, supplemental: dict | None) -> str:
    rs = trends.get("regional_summary", {})
    mkt_summaries = []
    for mkt_key, mkt_cfg in MARKETS.items():
        if mkt_key == "liberty":
            continue
        t = trends["markets"].get(mkt_key, {})
        rent = t.get("aggregate", {}).get("averageRent", {}).get("current")
        mom  = t.get("aggregate", {}).get("averageRent", {}).get("changes", {}).get("mom", {}).get("pct_change")
        temp = t.get("market_conditions", {}).get("temperature_label", "unknown")
        mkt_summaries.append(f"  {mkt_cfg['name']}: ${rent:,.0f} avg rent, {f'{mom:+.1f}%' if mom is not None else 'N/A'} MoM, {temp}")

    markets_str = "\n".join(mkt_summaries)

    dom_series = {
        mkt: recent_series(history, mkt, "averageDaysOnMarket", months=4)
        for mkt in MARKETS
    }
    listing_series = {
        mkt: recent_series(history, mkt, "totalListings", months=4)
        for mkt in MARKETS
    }

    return f"""Write the REGIONAL EXECUTIVE SUMMARY for the Upstate South Carolina rental market for {month}.

MARKET SNAPSHOT:
{markets_str}

Regional stats:
- Average MoM rent change across all markets: {f'{rs.get("avg_rent_mom_pct"):+.1f}%' if rs.get("avg_rent_mom_pct") is not None else 'N/A'}
- Hottest market: {MARKETS.get(rs.get('hottest_market', ''), {}).get('name', rs.get('hottest_market', 'N/A'))}
- Softest market: {MARKETS.get(rs.get('softest_market', ''), {}).get('name', rs.get('softest_market', 'N/A'))}
- Recent 4-month DOM series by market: {dom_series}
- Recent 4-month listings series by market: {listing_series}

SOURCE NOTES:
{source_context(supplemental, history)}

Write exactly TWO paragraphs with these headers on their own line:

UPSTATE SC MACRO VIEW
Open with a short sentence that sounds expert, then explain the takeaway in plain English.
Synthesize the regional story using only the current month and recent short trends provided.
Do not mention quarter-over-quarter or year-over-year data.
Do not mention Liberty by name in the regional summary.

OUTLOOK AND RISKS
What should owners watch over the next 3–6 months?
Focus on risks implied by recent rent, listings, and days-on-market trends.
End with one conservative action item for owners this month.
Include plain-text source citations using only the provided recent sources."""

# ─── Main ─────────────────────────────────────────────────────────────────────

def call_claude(prompt: str, context: str = "") -> str:
    messages = []
    if context:
        messages.append({"role": "user", "content": context})
        messages.append({"role": "assistant", "content": "Understood. Ready to analyze."})
    messages.append({"role": "user", "content": prompt})

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    return response.content[0].text.strip()

def main():
    print(f"\n{'='*55}")
    print("Insight Generator - Claude API")
    print(f"{'='*55}")

    trends = json.loads(TRENDS_FILE.read_text())
    history = json.loads(HISTORY_FILE.read_text()) if HISTORY_FILE.exists() else []
    supplemental = json.loads(SUPP_FILE.read_text()) if SUPP_FILE.exists() else {}
    month = trends.get("as_of", datetime.now().strftime("%Y-%m"))
    month_display = datetime.strptime(month, "%Y-%m").strftime("%B %Y")

    insights = {
        "generated_at": datetime.utcnow().isoformat(),
        "as_of": month,
        "regional": "",
        "markets": {},
    }

    # Regional summary first (gives context for per-market analysis)
    print("\nGenerating regional summary...")
    try:
        insights["regional"] = sanitize_regional_text(
            call_claude(regional_prompt(trends, month_display, history, supplemental))
        )
        print("  OK Regional summary done")
    except Exception as e:
        print(f"  ERROR Regional summary failed: {e}")
        insights["regional"] = "Regional analysis unavailable this month."

    # Per-market analysis
    for mkt_key, mkt_cfg in MARKETS.items():
        if mkt_key == "liberty":
            continue
        print(f"  Analyzing {mkt_cfg['name']}...")
        mkt_trends = trends["markets"].get(mkt_key, {})
        if not mkt_trends:
            insights["markets"][mkt_key] = "Insufficient data for analysis this month."
            continue
        try:
            prompt = market_prompt(mkt_key, mkt_cfg, mkt_trends, month_display, history, supplemental)
            insights["markets"][mkt_key] = sanitize_market_text(mkt_key, call_claude(prompt))
            print(f"  OK {mkt_cfg['name']}")
        except Exception as e:
            print(f"  ERROR {mkt_cfg['name']}: {e}")
            insights["markets"][mkt_key] = f"Analysis unavailable: {e}"

    insights["markets"]["liberty"] = "Hidden from dashboard due to low confidence and thin local signal."

    INSIGHTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    INSIGHTS_FILE.write_text(json.dumps(insights, indent=2))
    print(f"\nOK Insights saved -> {INSIGHTS_FILE.name}\n")

if __name__ == "__main__":
    main()
