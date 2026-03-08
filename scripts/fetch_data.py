#!/usr/bin/env python3
"""
fetch_data.py
Calls RentCast /markets endpoint for every configured zip code,
merges results by market, and appends a new month record to data/history.json.

Cost: 1 API call per zip code = 18 calls/month on the free plan (50 included).
"""

import os
import json
import time
import requests
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import ALL_ZIPS, ZIP_TO_MARKET, MARKETS, RENTCAST_BASE_URL, BEDROOM_SIZES

API_KEY = os.environ["RENTCAST_API_KEY"]
HISTORY_FILE = Path(__file__).parent.parent / "data" / "history.json"
RAW_FILE     = Path(__file__).parent.parent / "data" / "raw_latest.json"

HEADERS = {
    "X-Api-Key": API_KEY,
    "Accept": "application/json",
}

MAX_API_CALLS = 50
_call_count = 0

def fetch_zip(zip_code: str) -> dict | None:
    """Fetch /markets data for a single zip code."""
    global _call_count
    if _call_count >= MAX_API_CALLS:
        print(f"  ⛔ Skipping {zip_code} — API call limit of {MAX_API_CALLS} reached")
        return None

    url = f"{RENTCAST_BASE_URL}/markets"
    params = {"zipCode": zip_code, "historyMonths": 3}
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        r.raise_for_status()
        _call_count += 1
        print(f"  ✓ {zip_code} (call {_call_count}/{MAX_API_CALLS})")
        return r.json()
    except requests.HTTPError as e:
        print(f"  ✗ {zip_code} — HTTP {r.status_code}: {r.text[:120]}")
        return None
    except Exception as e:
        print(f"  ✗ {zip_code} — {e}")
        return None

def extract_rental_metrics(data: dict, bedrooms: int | None = None) -> dict:
    """Pull rent, DOM, and listing count from a RentCast market response.
    If bedrooms is None, pulls aggregate (all sizes).
    """
    rental = data.get("rentalData", {})

    if bedrooms is not None:
        key = f"{bedrooms}bedroom" if bedrooms <= 4 else f"{bedrooms}bedroom"
        bd = rental.get("bedrooms", {}).get(key, {})
        return {
            "averageRent":        bd.get("averageRent"),
            "medianRent":         bd.get("medianRent"),
            "averageDaysOnMarket": bd.get("averageDaysOnMarket"),
            "medianDaysOnMarket": bd.get("medianDaysOnMarket"),
            "totalListings":      bd.get("totalListings"),
            "newListings":        bd.get("newListings"),
        }
    else:
        return {
            "averageRent":        rental.get("averageRent"),
            "medianRent":         rental.get("medianRent"),
            "averageDaysOnMarket": rental.get("averageDaysOnMarket"),
            "medianDaysOnMarket": rental.get("medianDaysOnMarket"),
            "totalListings":      rental.get("totalListings"),
            "newListings":        rental.get("newListings"),
        }

def merge_zips_for_market(zip_results: list[dict]) -> dict:
    """Average numeric metrics across multiple zip codes for one market.
    Skips None values so sparse zips don't drag down averages.
    """
    metric_keys = [
        "averageRent", "medianRent",
        "averageDaysOnMarket", "medianDaysOnMarket",
        "totalListings", "newListings",
    ]
    merged = {}
    for key in metric_keys:
        vals = [r[key] for r in zip_results if r.get(key) is not None]
        merged[key] = round(sum(vals) / len(vals), 2) if vals else None

    # Merge bedroom breakdowns — sum listings, average rents/DOM
    merged["bedrooms"] = {}
    for b in BEDROOM_SIZES:
        bkey = str(b)
        rent_vals, dom_vals, listing_vals = [], [], []
        for r in zip_results:
            bd = r.get("bedrooms", {}).get(bkey, {})
            if bd.get("averageRent"):   rent_vals.append(bd["averageRent"])
            if bd.get("averageDaysOnMarket"): dom_vals.append(bd["averageDaysOnMarket"])
            if bd.get("totalListings"): listing_vals.append(bd["totalListings"])
        merged["bedrooms"][bkey] = {
            "averageRent":         round(sum(rent_vals)/len(rent_vals), 2) if rent_vals else None,
            "averageDaysOnMarket": round(sum(dom_vals)/len(dom_vals), 2)   if dom_vals  else None,
            "totalListings":       sum(listing_vals) if listing_vals else None,
        }
    return merged

def build_month_record(run_date: datetime, all_zip_data: dict) -> dict:
    """Aggregate all zip data into a single month record keyed by market."""
    record = {
        "month": run_date.strftime("%Y-%m"),
        "fetched_at": run_date.isoformat(),
        "markets": {},
    }

    for mkt_key, mkt_cfg in MARKETS.items():
        zip_results = []
        for z in mkt_cfg["zips"]:
            raw = all_zip_data.get(z)
            if raw is None:
                continue
            agg = extract_rental_metrics(raw)
            agg["bedrooms"] = {}
            for b in BEDROOM_SIZES:
                agg["bedrooms"][str(b)] = extract_rental_metrics(raw, bedrooms=b)
            zip_results.append(agg)

        if not zip_results:
            print(f"  ⚠ {mkt_key}: no data from any zip")
            record["markets"][mkt_key] = None
        else:
            record["markets"][mkt_key] = merge_zips_for_market(zip_results)
            print(f"  ✓ {mkt_key}: merged {len(zip_results)} zip(s)")

    return record

def load_history() -> list:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return []

def save_history(history: list):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, indent=2))

def main():
    run_date = datetime.now(timezone.utc)
    current_month = run_date.strftime("%Y-%m")
    print(f"\n{'='*55}")
    print(f"RentCast Fetch — {run_date.strftime('%B %Y')}")
    print(f"{'='*55}")
    print(f"\nFetching {len(ALL_ZIPS)} zip codes...")

    all_zip_data = {}
    for i, z in enumerate(ALL_ZIPS):
        result = fetch_zip(z)
        if result:
            all_zip_data[z] = result
        if i < len(ALL_ZIPS) - 1:
            time.sleep(0.5)

    # Save raw snapshot for debugging
    RAW_FILE.parent.mkdir(parents=True, exist_ok=True)
    RAW_FILE.write_text(json.dumps(all_zip_data, indent=2))
    print(f"\nRaw data saved → {RAW_FILE.name}")

    print("\nMerging by market...")
    month_record = build_month_record(run_date, all_zip_data)

    # Load history, replace current month if already exists, else append
    history = load_history()
    existing = [i for i, r in enumerate(history) if r.get("month") == current_month]
    if existing:
        history[existing[0]] = month_record
        print(f"\nReplaced existing record for {current_month}")
    else:
        history.append(month_record)
        print(f"\nAppended new record for {current_month} ({len(history)} months total)")

    save_history(history)
    print(f"History saved → {HISTORY_FILE.name}")
    print(f"\n✅ Fetch complete — {len(all_zip_data)}/{len(ALL_ZIPS)} zips returned data")
    print(f"   API calls used: {_call_count}/{MAX_API_CALLS}\n")

if __name__ == "__main__":
    main()
