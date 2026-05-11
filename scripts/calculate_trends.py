#!/usr/bin/env python3
"""
calculate_trends.py
Reads data/history.json and computes MoM, QoQ, YoY percentage changes
for every market and metric. Writes results to data/trends.json.
"""

import json
from pathlib import Path
from datetime import datetime
from config import MARKETS, BEDROOM_SIZES

HISTORY_FILE = Path(__file__).parent.parent / "data" / "history.json"
TRENDS_FILE  = Path(__file__).parent.parent / "data" / "trends.json"
DOM_AUDIT_FILE = Path(__file__).parent.parent / "data" / "rentcast_dom_audit.json"

WINDOWS = {"mom": 1, "qoq": 3, "yoy": 12}
HIGH_CONFIDENCE_MARKETS = ["greenville", "spartanburg"]

# Minimum months of history required before a window is considered reliable.
# Values below the threshold are calculated and stored but flagged as unreliable.
MIN_MONTHS = {"mom": 2, "qoq": 6, "yoy": 14}

def pct_change(old, new):
    if old is None or new is None or old == 0:
        return None
    return round(((new - old) / old) * 100, 2)

def get_month(history: list, offset: int) -> dict | None:
    """Get the month record exactly `offset` calendar months back from the latest."""
    if not history:
        return None
    latest_month = history[-1].get("month")
    if not latest_month:
        return None
    target_month = shift_month(latest_month, -offset)
    for record in reversed(history):
        if record.get("month") == target_month:
            return record
    return None


def shift_month(month_str: str, delta: int) -> str | None:
    try:
        dt = datetime.strptime(month_str, "%Y-%m")
    except ValueError:
        return None
    total_months = dt.year * 12 + (dt.month - 1) + delta
    if total_months < 0:
        return None
    year = total_months // 12
    month = total_months % 12 + 1
    return f"{year:04d}-{month:02d}"

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


def dom_audit_val(dom_audit: dict, month: str | None, market: str) -> float | None:
    if not month:
        return None
    return (
        dom_audit.get("markets", {})
        .get(market, {})
        .get("months", {})
        .get(month, {})
        .get("weighted_averageDaysOnMarket")
    )

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

def weighted_average(pairs):
    usable = [(value, weight) for value, weight in pairs if value is not None and weight is not None and weight > 0]
    if not usable:
        return None
    total_weight = sum(weight for _, weight in usable)
    if total_weight == 0:
        return None
    return round(sum(value * weight for value, weight in usable) / total_weight, 2)

def compute_trends(history: list, dom_audit: dict | None = None) -> dict:
    history = sorted(history, key=lambda record: record.get("month", ""))
    latest = history[-1] if history else None
    if latest is None:
        return {}

    trends = {
        "as_of": latest.get("month"),
        "months_of_history": len(history),
        "markets": {},
    }
    latest_month = latest.get("month")

    for mkt_key in MARKETS:
        mkt_trends = {
            "aggregate": {},
            "bedrooms": {},
            "market_conditions": {},
        }

        # ── Aggregate metrics ──────────────────────────────────────────────
        for metric in ["averageRent", "medianRent", "averageDaysOnMarket",
                       "medianDaysOnMarket", "totalListings", "newListings"]:
            if metric == "averageDaysOnMarket":
                current = dom_audit_val(dom_audit or {}, latest.get("month"), mkt_key)
            else:
                current = market_val(latest, mkt_key, metric)
            metric_data = {"current": current, "changes": {}}

            for label, offset in WINDOWS.items():
                ref = get_month(history, offset)
                if metric == "averageDaysOnMarket":
                    ref_month = shift_month(latest_month, -offset) if latest_month else None
                    ref_val = dom_audit_val(dom_audit or {}, ref_month, mkt_key)
                else:
                    ref_val = market_val(ref, mkt_key, metric)
                pct = pct_change(ref_val, current)
                reliable = len(history) >= MIN_MONTHS[label]
                anomaly = (
                    label == "mom"
                    and metric in ["averageRent", "medianRent"]
                    and pct is not None
                    and abs(pct) > 5
                )
                metric_data["changes"][label] = {
                    "reference_value": ref_val,
                    "pct_change": pct if reliable else None,
                    "pct_change_raw": pct,          # always stored for future use
                    "direction": direction(pct) if reliable else "flat",
                    "signal": signal(metric, pct) if reliable else "insufficient data",
                    "reliable": reliable,
                    "anomaly_flag": anomaly,
                    "anomaly_note": (
                        "Unusual monthly rent move; verify against sample depth and recent baseline."
                        if anomaly else None
                    ),
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
                    reliable = len(history) >= MIN_MONTHS[label]
                    anomaly = (
                        label == "mom"
                        and metric == "averageRent"
                        and pct is not None
                        and abs(pct) > 5
                    )
                    m_data["changes"][label] = {
                        "reference_value": ref_val,
                        "pct_change": pct if reliable else None,
                        "pct_change_raw": pct,          # always stored for future use
                        "direction": direction(pct) if reliable else "flat",
                        "signal": signal(metric, pct) if reliable else "insufficient data",
                        "reliable": reliable,
                        "anomaly_flag": anomaly,
                        "anomaly_note": (
                            "Unusual monthly bedroom-rent move; verify against sample depth and recent baseline."
                            if anomaly else None
                        ),
                    }
                bed_data[metric] = m_data
            mkt_trends["bedrooms"][bkey] = bed_data

        # ── Market conditions summary ──────────────────────────────────────
        # Synthesize a market temperature from current pricing and lease-up conditions.
        # This intentionally avoids leaning on YoY growth, which can lag the current market.
        rent_mom   = mkt_trends["aggregate"]["averageRent"]["changes"]["mom"]["pct_change"]
        dom_mom    = mkt_trends["aggregate"]["averageDaysOnMarket"]["changes"]["mom"]["pct_change"]
        inv_mom    = mkt_trends["aggregate"]["totalListings"]["changes"]["mom"]["pct_change"]

        # Score: current rent pressure + faster lease-up + tighter inventory = landlord-leaning market
        score = 0
        if rent_mom is not None:
            score += 1 if rent_mom > 1 else -1 if rent_mom < -1 else 0
        if dom_mom is not None:
            score += 1 if dom_mom < -3 else -1 if dom_mom > 3 else 0
        if inv_mom is not None:
            score += 1 if inv_mom < -5 else -1 if inv_mom > 8 else 0

        if score >= 2:
            temp = "hot"
            temp_label = "Landlord-Favored"
        elif score >= 1:
            temp = "warm"
            temp_label = "Slightly Landlord-Favored"
        elif score == 0:
            temp = "neutral"
            temp_label = "Balanced Market"
        elif score == -1:
            temp = "cool"
            temp_label = "Slightly Renter-Favored"
        else:
            temp = "cold"
            temp_label = "Renter's Market"

        mkt_trends["market_conditions"] = {
            "temperature": temp,
            "temperature_label": temp_label,
            "score": score,
            "rent_mom_pct": rent_mom,
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
    all_mom = [
        trends["markets"][m]["aggregate"]["averageRent"]["changes"]["mom"]["pct_change"]
        for m in MARKETS
        if trends["markets"][m]["aggregate"]["averageRent"]["changes"]["mom"]["pct_change"] is not None
    ]
    all_dom_mom = [
        (
            trends["markets"][m]["aggregate"]["averageDaysOnMarket"]["changes"]["mom"]["pct_change"],
            trends["markets"][m]["aggregate"]["totalListings"]["current"],
        )
        for m in MARKETS
    ]
    all_dom_qoq = [
        (
            trends["markets"][m]["aggregate"]["averageDaysOnMarket"]["changes"]["qoq"]["pct_change"],
            trends["markets"][m]["aggregate"]["totalListings"]["current"],
        )
        for m in MARKETS
    ]
    trends["regional_summary"] = {
        "avg_rent_mom_pct": round(sum(all_mom) / len(all_mom), 2) if all_mom else None,
        "avg_rent_yoy_pct": round(sum(all_yoy) / len(all_yoy), 2) if all_yoy else None,
        "avg_rent_qoq_pct": weighted_average([
            (
                trends["markets"][m]["aggregate"]["averageRent"]["changes"]["qoq"]["pct_change"],
                trends["markets"][m]["aggregate"]["totalListings"]["current"],
            )
            for m in MARKETS
        ]),
        "avg_dom_mom_pct": weighted_average(all_dom_mom),
        "avg_dom_qoq_pct": weighted_average(all_dom_qoq),
        "markets_with_rent_growth": sum(1 for v in all_yoy if v > 0),
        "markets_declining": sum(1 for v in all_yoy if v < 0),
        "hottest_market": max(HIGH_CONFIDENCE_MARKETS, key=lambda m:
            trends["markets"][m]["aggregate"]["averageRent"]["changes"]["mom"]["pct_change"] or -999),
        "softest_market": min(HIGH_CONFIDENCE_MARKETS, key=lambda m:
            trends["markets"][m]["aggregate"]["averageRent"]["changes"]["mom"]["pct_change"] or 999),
        "top_market_scope": "high_confidence_only",
    }

    return trends

def main():
    print(f"\n{'='*55}")
    print("Trend Calculator")
    print(f"{'='*55}")

    if not HISTORY_FILE.exists():
        print("ERROR history.json not found - run fetch_data.py first")
        return

    history = json.loads(HISTORY_FILE.read_text())
    history.sort(key=lambda record: record.get("month", ""))
    print(f"Loaded {len(history)} months of history")

    dom_audit = json.loads(DOM_AUDIT_FILE.read_text()) if DOM_AUDIT_FILE.exists() else {}
    trends = compute_trends(history, dom_audit)

    TRENDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRENDS_FILE.write_text(json.dumps(trends, indent=2))
    print(f"OK Trends saved -> {TRENDS_FILE.name}")

    # Print quick summary
    print(f"\nRegional Summary - {trends.get('as_of')}:")
    rs = trends.get("regional_summary", {})
    print(f"  Avg MoM rent change: {rs.get('avg_rent_mom_pct')}%")
    print(f"  Avg MoM DOM change: {rs.get('avg_dom_mom_pct')}%")
    print(f"  Hottest: {rs.get('hottest_market')} | Softest: {rs.get('softest_market')}\n")

if __name__ == "__main__":
    main()
