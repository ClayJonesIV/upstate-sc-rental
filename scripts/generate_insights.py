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

sys_path = str(Path(__file__).parent)
import sys
sys.path.insert(0, sys_path)
from config import MARKETS

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ─── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior real estate market analyst specializing in the Upstate South Carolina rental market.
You write institutional-quality market reports for rental property owners and real estate investors.
Your analysis is direct, data-driven, and actionable — you give specific percentage recommendations,
not vague guidance. You understand the nuances of small Sun Belt markets, college-town seasonality,
and the relationship between industrial job growth (BMW, Michelin, Inland Port) and rental demand.
Write in a professional but accessible tone. No bullet points — flowing narrative paragraphs only.
Be specific: cite the actual numbers from the data provided."""

def market_prompt(mkt_key: str, mkt_cfg: dict, mkt_trends: dict, month: str) -> str:
    agg = mkt_trends["aggregate"]
    cond = mkt_trends["market_conditions"]
    beds = mkt_trends["bedrooms"]

    rent_cur  = agg["averageRent"]["current"]
    rent_mom  = agg["averageRent"]["changes"]["mom"]["pct_change"]
    rent_qoq  = agg["averageRent"]["changes"]["qoq"]["pct_change"]
    rent_yoy  = agg["averageRent"]["changes"]["yoy"]["pct_change"]
    dom_cur   = agg["averageDaysOnMarket"]["current"]
    dom_mom   = agg["averageDaysOnMarket"]["changes"]["mom"]["pct_change"]
    dom_yoy   = agg["averageDaysOnMarket"]["changes"]["yoy"]["pct_change"]
    inv_cur   = agg["totalListings"]["current"]
    inv_mom   = agg["totalListings"]["changes"]["mom"]["pct_change"]
    inv_yoy   = agg["totalListings"]["changes"]["yoy"]["pct_change"]

    bed_summary = ""
    for b in ["1", "2", "3", "4"]:
        bd = beds.get(b, {})
        r = bd.get("averageRent", {}).get("current")
        r_yoy = bd.get("averageRent", {}).get("changes", {}).get("yoy", {}).get("pct_change")
        d = bd.get("averageDaysOnMarket", {}).get("current")
        if r:
            bed_summary += f"\n  {b}BR: avg rent ${r:,.0f}" + (f", {r_yoy:+.1f}% YoY" if r_yoy else "") + (f", DOM {d:.0f}d" if d else "")

    notes = mkt_cfg.get("notes", "")
    notes_line = f"\nMarket notes: {notes}" if notes else ""

    return f"""Write a deep narrative analysis for the {mkt_cfg['name']} rental market ({mkt_cfg['label']}) for {month}.
{notes_line}

CURRENT DATA:
- Market temperature: {cond['temperature_label']} (score: {cond['score']})
- Average rent: ${rent_cur:,.0f} if rent_cur else 'N/A'
  - MoM: {f'{rent_mom:+.1f}%' if rent_mom is not None else 'N/A'}
  - QoQ: {f'{rent_qoq:+.1f}%' if rent_qoq is not None else 'N/A'}
  - YoY: {f'{rent_yoy:+.1f}%' if rent_yoy is not None else 'N/A'}
- Days on market: {f'{dom_cur:.0f}' if dom_cur else 'N/A'} days
  - MoM: {f'{dom_mom:+.1f}%' if dom_mom is not None else 'N/A'}
  - YoY: {f'{dom_yoy:+.1f}%' if dom_yoy is not None else 'N/A'}
- Active listings: {f'{inv_cur:,.0f}' if inv_cur else 'N/A'}
  - MoM: {f'{inv_mom:+.1f}%' if inv_mom is not None else 'N/A'}
  - YoY: {f'{inv_yoy:+.1f}%' if inv_yoy is not None else 'N/A'}
- By bedroom:{bed_summary}

Write exactly FOUR paragraphs with these headers on their own line before each:

MARKET CONDITIONS
Describe what the data reveals about current supply/demand dynamics. Reference specific numbers.
Explain what is driving these conditions (employment, new construction, seasonality, migration).
Compare to where this market was 12 months ago.

IMPLICATIONS FOR CURRENT OWNERS
What does this data mean for someone who already owns rentals here?
Should they feel confident, cautious, or proactive? 
Discuss cash flow implications, risk of vacancy, and portfolio positioning.

VACANCY MARKETING STRATEGY
Give specific, actionable marketing recommendations for a landlord with a vacancy right now.
Include: what platforms to prioritize, how to price the listing relative to market averages,
what amenities or lease terms to emphasize, ideal listing timing, and concession strategy
(offer one? hold firm?). Be specific — name platforms, pricing tactics, lease length suggestions.

RENEWAL PRICING STRATEGY
Give a concrete recommendation: raise rent, hold rent, or lower rent at renewal.
Specify the recommended percentage range and reasoning.
Address different scenarios: strong tenant vs. at-risk tenant.
Discuss timing — when to send renewal notices and how far in advance.
Include the financial math: cost of turnover vs. cost of holding rent."""

def regional_prompt(trends: dict, month: str) -> str:
    rs = trends.get("regional_summary", {})
    mkt_summaries = []
    for mkt_key, mkt_cfg in MARKETS.items():
        t = trends["markets"].get(mkt_key, {})
        rent = t.get("aggregate", {}).get("averageRent", {}).get("current")
        yoy  = t.get("aggregate", {}).get("averageRent", {}).get("changes", {}).get("yoy", {}).get("pct_change")
        temp = t.get("market_conditions", {}).get("temperature_label", "unknown")
        mkt_summaries.append(f"  {mkt_cfg['name']}: ${rent:,.0f} avg rent, {f'{yoy:+.1f}%' if yoy else 'N/A'} YoY, {temp}")

    markets_str = "\n".join(mkt_summaries)

    return f"""Write the REGIONAL EXECUTIVE SUMMARY for the Upstate South Carolina rental market for {month}.

MARKET SNAPSHOT:
{markets_str}

Regional stats:
- Average YoY rent change across all markets: {f'{rs.get("avg_rent_yoy_pct"):+.1f}%' if rs.get("avg_rent_yoy_pct") else 'N/A'}
- Markets with rent growth: {rs.get('markets_with_rent_growth', 'N/A')}
- Markets declining: {rs.get('markets_declining', 'N/A')}
- Hottest market: {MARKETS.get(rs.get('hottest_market', ''), {}).get('name', rs.get('hottest_market', 'N/A'))}
- Softest market: {MARKETS.get(rs.get('softest_market', ''), {}).get('name', rs.get('softest_market', 'N/A'))}

Write exactly THREE paragraphs with these headers on their own line:

UPSTATE SC MACRO VIEW
Synthesize the regional story. What is the overall direction of the Upstate market?
Discuss how the five primary markets (Greenville, Spartanburg, Anderson, Simpsonville, Greer)
compare to the foothills markets (Easley, Piedmont, Liberty, Clemson, Seneca).
Reference the BMW/Michelin/Inland Port employment base, Sun Belt migration trends,
and new apartment supply pipeline where relevant.

CROSS-MARKET INVESTMENT THESIS
Where in the Upstate should a new investor be looking right now, and why?
Compare risk/reward profiles across markets. Which markets offer the best
cap rate potential vs. appreciation vs. stability? Are there any contrarian
opportunities in softer markets? Be direct with a recommendation.

OUTLOOK AND RISKS
What should owners watch over the next 3–6 months?
What are the key risks to the current market (new supply deliveries, interest rate changes,
employer announcements, seasonal slowdown)? What leading indicators should owners track?
End with the single most important action item for Upstate SC rental owners this month."""

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
    print("Insight Generator — Claude API")
    print(f"{'='*55}")

    trends = json.loads(TRENDS_FILE.read_text())
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
        insights["regional"] = call_claude(regional_prompt(trends, month_display))
        print("  ✓ Regional summary done")
    except Exception as e:
        print(f"  ✗ Regional summary failed: {e}")
        insights["regional"] = "Regional analysis unavailable this month."

    # Per-market analysis
    for mkt_key, mkt_cfg in MARKETS.items():
        print(f"  Analyzing {mkt_cfg['name']}...")
        mkt_trends = trends["markets"].get(mkt_key, {})
        if not mkt_trends:
            insights["markets"][mkt_key] = "Insufficient data for analysis this month."
            continue
        try:
            prompt = market_prompt(mkt_key, mkt_cfg, mkt_trends, month_display)
            insights["markets"][mkt_key] = call_claude(prompt)
            print(f"  ✓ {mkt_cfg['name']}")
        except Exception as e:
            print(f"  ✗ {mkt_cfg['name']}: {e}")
            insights["markets"][mkt_key] = f"Analysis unavailable: {e}"

    INSIGHTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    INSIGHTS_FILE.write_text(json.dumps(insights, indent=2))
    print(f"\n✅ Insights saved → {INSIGHTS_FILE.name}\n")

if __name__ == "__main__":
    main()
