#!/usr/bin/env python3
"""
calculate_trends.py
Reads data/history.json and computes MoM, QoQ, YoY percentage changes
for every market and metric. Writes results to data/trends.json.
"""

import json
from pathlib import Path
from config import MARKETS, BEDROOM_SIZES

HISTORY_FILE = Path(__file__).parent.parent / "data" / "history.json"
TRENDS_FILE  = Path(__file__).parent.parent / "data" / "trends.json"

WINDOWS = {"mom": 1, "qoq": 3, "yoy": 12}

def pct_change(old, new):
    if old is None or new is None or old == 0:
        return None
    return round(((new - old) / old) * 100, 2)

def get_month(history: list, offset: int) -> dict | None:
    """Get the month record at `offset` months back from the latest."""
    if len(history) <= offset:
        return None
    return history[-(offset + 1)]

def market_val(record: dict, market: str, metric: str, bedroom: str | None = None):
    """Extract a single metric value from a month record."""
    if record is None:
        return None
    mkt = record.get("markets", {}).get(market)
    if mkt is None:
        return None
    if bedroom is not None:
        return mkt.get("bedrooms", {}).get(bedroom, {}).get(metric)
    return mkt.get(metric)

def direction(pct):
    if pct is None: return "flat"
    if pct > 2:  return "up"
    if pct < -2: return "down"
    return "flat"

def signal(metric, pct):
    """Translate a % change into a plain-English signal for insights."""
    if pct is None: return "insufficient data"
    if metric in ["averageRent", "medianRent"]:
        if pct >= 5:  return "strong rent growth"
        if pct >= 2:  return "moderate rent growth"
        if pct >= 0:  return "stable rents"
        if pct >= -2: return "mild softening"
        return "notable rent decline"
    if metric in ["averageDaysOnMarket", "medianDaysOnMarket"]:
        # Inverse: faster DOM = tighter market
        if pct <= -15: return "market tightening sharply"
        if pct <= -5:  return "market tightening"
        if pct <= 5:   return "market stable"
        if pct <= 15:  return "market loosening"
        return "market loosening significantly"
    if metric in ["totalListings", "newListings"]:
        if pct >= 15: return "supply building rapidly"
        if pct >= 5:  return "supply increasing"
        if pct >= -5: return "supply stable"
        if pct >= -15: return "supply tightening"
        return "supply very tight"
    return "changed"

def compute_trends(history: list) -> dict:
    latest = history[-1] if history else None
    if latest is None:
        return {}

    trends = {
        "as_of": latest.get("month"),
        "months_of_history": len(history),
        "markets": {},
    }

    for mkt_key in MARKETS:
        mkt_trends = {
            "aggregate": {},
            "bedrooms": {},
            "market_conditions": {},
        }

        # ── Aggregate metrics ──────────────────────────────────────────────
        for metric in ["averageRent", "medianRent", "averageDaysOnMarket",
                       "medianDaysOnMarket", "totalListings", "newListings"]:
            current = market_val(latest, mkt_key, metric)
            metric_data = {"current": current, "changes": {}}

            for label, offset in WINDOWS.items():
                ref = get_month(history, offset)
                ref_val = market_val(ref, mkt_key, metric)
                pct = pct_change(ref_val, current)
                metric_data["changes"][label] = {
                    "reference_value": ref_val,
                    "pct_change": pct,
                    "direction": direction(pct),
                    "signal": signal(metric, pct),
                }

            mkt_trends["aggregate"][metric] = metric_data

        # ── Bedroom breakdowns ─────────────────────────────────────────────
        for b in BEDROOM_SIZES:
            bkey = str(b)
            bed_data = {}
            for metric in ["averageRent", "averageDaysOnMarket", "totalListings"]:
                current = market_val(latest, mkt_key, metric, bedroom=bkey)
                m_data = {"current": current, "changes": {}}
                for label, offset in WINDOWS.items():
                    ref = get_month(history, offset)
                    ref_val = market_val(ref, mkt_key, metric, bedroom=bkey)
                    pct = pct_change(ref_val, current)
                    m_data["changes"][label] = {
                        "reference_value": ref_val,
                        "pct_change": pct,
                        "direction": direction(pct),
                        "signal": signal(metric, pct),
                    }
                bed_data[metric] = m_data
            mkt_trends["bedrooms"][bkey] = bed_data

        # ── Market conditions summary ──────────────────────────────────────
        # Synthesize a simple market temperature from rent growth + DOM trend
        rent_mom   = mkt_trends["aggregate"]["averageRent"]["changes"]["mom"]["pct_change"]
        rent_yoy   = mkt_trends["aggregate"]["averageRent"]["changes"]["yoy"]["pct_change"]
        dom_mom    = mkt_trends["aggregate"]["averageDaysOnMarket"]["changes"]["mom"]["pct_change"]
        inv_mom    = mkt_trends["aggregate"]["totalListings"]["changes"]["mom"]["pct_change"]

        # Score: rent up + DOM down + inventory down = landlord market
        score = 0
        if rent_yoy is not None:
            score += 2 if rent_yoy > 3 else 1 if rent_yoy > 0 else -1 if rent_yoy > -3 else -2
        if dom_mom is not None:
            score += 1 if dom_mom < -5 else -1 if dom_mom > 5 else 0
        if inv_mom is not None:
            score += 1 if inv_mom < -5 else -1 if inv_mom > 10 else 0

        if score >= 3:
            temp = "hot"
            temp_label = "Landlord's Market"
        elif score >= 1:
            temp = "warm"
            temp_label = "Slightly Landlord-Favored"
        elif score >= -1:
            temp = "neutral"
            temp_label = "Balanced Market"
        elif score >= -2:
            temp = "cool"
            temp_label = "Slightly Renter-Favored"
        else:
            temp = "cold"
            temp_label = "Renter's Market"

        mkt_trends["market_conditions"] = {
            "temperature": temp,
            "temperature_label": temp_label,
            "score": score,
            "rent_yoy_pct": rent_yoy,
            "dom_mom_direction": direction(dom_mom),
            "inventory_mom_direction": direction(inv_mom),
        }

        trends["markets"][mkt_key] = mkt_trends

    # ── Regional summary ───────────────────────────────────────────────────
    all_yoy = [
        trends["markets"][m]["aggregate"]["averageRent"]["changes"]["yoy"]["pct_change"]
        for m in MARKETS
        if trends["markets"][m]["aggregate"]["averageRent"]["changes"]["yoy"]["pct_change"] is not None
    ]
    trends["regional_summary"] = {
        "avg_rent_yoy_pct": round(sum(all_yoy) / len(all_yoy), 2) if all_yoy else None,
        "markets_with_rent_growth": sum(1 for v in all_yoy if v > 0),
        "markets_declining": sum(1 for v in all_yoy if v < 0),
        "hottest_market": max(MARKETS.keys(), key=lambda m:
            trends["markets"][m]["aggregate"]["averageRent"]["changes"]["yoy"]["pct_change"] or -999),
        "softest_market": min(MARKETS.keys(), key=lambda m:
            trends["markets"][m]["aggregate"]["averageRent"]["changes"]["yoy"]["pct_change"] or 999),
    }

    return trends

def main():
    print(f"\n{'='*55}")
    print("Trend Calculator")
    print(f"{'='*55}")

    if not HISTORY_FILE.exists():
        print("✗ history.json not found — run fetch_data.py first")
        return

    history = json.loads(HISTORY_FILE.read_text())
    print(f"Loaded {len(history)} months of history")

    trends = compute_trends(history)

    TRENDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRENDS_FILE.write_text(json.dumps(trends, indent=2))
    print(f"✅ Trends saved → {TRENDS_FILE.name}")

    # Print quick summary
    print(f"\nRegional Summary — {trends.get('as_of')}:")
    rs = trends.get("regional_summary", {})
    print(f"  Avg YoY rent change: {rs.get('avg_rent_yoy_pct')}%")
    print(f"  Markets growing: {rs.get('markets_with_rent_growth')} | Declining: {rs.get('markets_declining')}")
    print(f"  Hottest: {rs.get('hottest_market')} | Softest: {rs.get('softest_market')}\n")

if __name__ == "__main__":
    main()
