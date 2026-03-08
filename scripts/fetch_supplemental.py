#!/usr/bin/env python3
"""
fetch_supplemental.py
Pulls FREE public rental data from two sources to supplement RentCast:

  1. Apartment List  — monthly city-level rent estimates by bedroom size
     URL: https://www.apartmentlist.com/research/data
     CSV updated the first week of each month, no API key needed.

  2. Zillow Research — ZORI (Zillow Observed Rent Index) by zip code
     URL: https://www.zillow.com/research/data/
     CSV updated monthly, no API key needed.

Both sources provide bedroom-level breakdowns that RentCast's free
/markets endpoint does not return. Results are merged into a
data/supplemental_latest.json file that fetch_data.py will blend
into history.json during the monthly run.

No API keys required. Pure public data.
"""

import csv
import json
import io
import time
import requests
from pathlib import Path
from datetime import datetime, timezone
import sys

sys.path.insert(0, str(Path(__file__).parent))
from config import MARKETS

SUPP_FILE = Path(__file__).parent.parent / "data" / "supplemental_latest.json"

# ── Apartment List URLs ────────────────────────────────────────────────────────
# Apartment List publishes separate CSVs per bedroom count.
# These are stable URLs that update in-place each month.
ALIST_URLS = {
    "1": "https://www.apartmentlist.com/research/data/city-1br.csv",
    "2": "https://www.apartmentlist.com/research/data/city-2br.csv",
}

# ── Zillow ZORI URLs ──────────────────────────────────────────────────────────
# Zillow publishes separate all-bedroom and per-bedroom ZORI CSVs.
# The zip-level file is the most granular we can get for free.
ZILLOW_URLS = {
    "all": "https://files.zillowstatic.com/research/public_csvs/zori/Zip_zori_uc_sfrcondomfr_sm_month.csv",
    "1":   "https://files.zillowstatic.com/research/public_csvs/zori/Zip_zori_uc_sfrcondomfr_sm_month.csv",
}
# Zillow also provides city-level ZORI (smoother signal for small markets)
ZILLOW_CITY_URL = "https://files.zillowstatic.com/research/public_csvs/zori/City_zori_uc_sfrcondomfr_sm_month.csv"

HEADERS = {"User-Agent": "Mozilla/5.0 (research/data pull; contact via github)"}
TIMEOUT = 45


# ── Market city/state mapping for name matching ────────────────────────────────
# Keys match MARKETS keys; values are (city, state) tuples for CSV lookups.
MARKET_CITIES = {
    "greenville":  [("Greenville", "SC")],
    "spartanburg": [("Spartanburg", "SC")],
    "anderson":    [("Anderson", "SC")],
    "simpsonville":[("Simpsonville", "SC")],
    "greer":       [("Greer", "SC")],
    "easley":      [("Easley", "SC")],
    "piedmont":    [("Piedmont", "SC")],
    "liberty":     [("Liberty", "SC")],
    "clemson":     [("Clemson", "SC")],
    "seneca":      [("Seneca", "SC")],
}


def fetch_csv(url: str, label: str) -> list[dict] | None:
    """Download a CSV URL and return list of row dicts."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        reader = csv.DictReader(io.StringIO(r.text))
        rows = list(reader)
        print(f"  ✓ {label}: {len(rows):,} rows")
        return rows
    except Exception as e:
        print(f"  ✗ {label}: {e}")
        return None


def latest_month_col(headers: list[str]) -> str | None:
    """Find the most recent YYYY-MM date column in a Zillow CSV."""
    date_cols = [h for h in headers if len(h) == 7 and h[4] == "-"]
    if not date_cols:
        return None
    return sorted(date_cols)[-1]


def parse_apartment_list(rows: list[dict], bedroom: str) -> dict:
    """
    Extract latest rent per market city from Apartment List CSV.
    Returns {market_key: rent_float}
    """
    # Find the most recent month column (format: YYYY_MM)
    date_cols = [k for k in rows[0].keys() if k[:2] == "20" and "_" in k]
    if not date_cols:
        return {}
    latest_col = sorted(date_cols)[-1]

    # Build lookup: (city_lower, state) -> rent
    lookup = {}
    for row in rows:
        city  = row.get("city_name", row.get("city", "")).strip()
        state = row.get("state", "").strip().upper()
        val   = row.get(latest_col, "")
        try:
            rent = float(val.replace(",", "").replace("$", ""))
            lookup[(city.lower(), state)] = rent
        except (ValueError, AttributeError):
            pass

    result = {}
    for mkt_key, cities in MARKET_CITIES.items():
        for city, state in cities:
            rent = lookup.get((city.lower(), state.upper()))
            if rent:
                result[mkt_key] = rent
                break

    return result


def parse_zillow_city(rows: list[dict]) -> dict:
    """
    Extract latest ZORI rent per market city from Zillow city-level CSV.
    Returns {market_key: rent_float}
    """
    if not rows:
        return {}
    headers = list(rows[0].keys())
    latest_col = latest_month_col(headers)
    if not latest_col:
        return {}

    lookup = {}
    for row in rows:
        city  = row.get("RegionName", "").strip()
        state = row.get("StateName", "").strip().upper()
        val   = row.get(latest_col, "")
        try:
            rent = float(val)
            lookup[(city.lower(), state)] = rent
        except (ValueError, TypeError):
            pass

    result = {}
    for mkt_key, cities in MARKET_CITIES.items():
        for city, state in cities:
            rent = lookup.get((city.lower(), state.upper()))
            if rent:
                result[mkt_key] = rent
                break

    return result


def parse_zillow_zip(rows: list[dict], target_zips: set) -> dict:
    """
    Extract latest ZORI rent per zip from Zillow zip-level CSV.
    Returns {zip_str: rent_float}
    """
    if not rows:
        return {}
    headers = list(rows[0].keys())
    latest_col = latest_month_col(headers)
    if not latest_col:
        return {}

    result = {}
    for row in rows:
        zip_code = str(row.get("RegionName", "")).strip().zfill(5)
        if zip_code not in target_zips:
            continue
        val = row.get(latest_col, "")
        try:
            result[zip_code] = float(val)
        except (ValueError, TypeError):
            pass

    return result


def aggregate_zips_to_market(zip_rents: dict) -> dict:
    """Average zip-level Zillow rents up to market level."""
    result = {}
    for mkt_key, mkt_cfg in MARKETS.items():
        vals = [zip_rents[z] for z in mkt_cfg["zips"] if z in zip_rents]
        if vals:
            result[mkt_key] = round(sum(vals) / len(vals), 2)
    return result


def build_supplemental(
    alist_1br: dict,
    alist_2br: dict,
    zillow_city: dict,
    zillow_zip: dict,
) -> dict:
    """
    Merge all supplemental sources into a per-market structure.

    Bedroom rent priority:
      1BR → Apartment List 1BR (most granular)
      2BR → Apartment List 2BR
      3BR → Zillow city ZORI * 1.18  (typical 3BR premium over market avg)
      4BR → Zillow city ZORI * 1.35

    Overall market avg → weighted blend of Zillow city + zip average.
    """
    run_date = datetime.now(timezone.utc)
    supp = {
        "fetched_at": run_date.isoformat(),
        "month": run_date.strftime("%Y-%m"),
        "sources": ["apartment_list", "zillow_research"],
        "markets": {},
    }

    for mkt_key in MARKETS:
        z_city = zillow_city.get(mkt_key)
        z_zip  = zillow_zip.get(mkt_key)

        # Blend Zillow signals for overall avg (prefer zip-level when available)
        zillow_avg = None
        if z_zip and z_city:
            zillow_avg = round((z_zip * 0.6 + z_city * 0.4), 2)
        elif z_zip:
            zillow_avg = z_zip
        elif z_city:
            zillow_avg = z_city

        # Per-bedroom estimates
        bedrooms = {}
        for b in ["1", "2", "3", "4"]:
            rent = None
            source = None
            if b == "1" and alist_1br.get(mkt_key):
                rent = alist_1br[mkt_key]
                source = "apartment_list"
            elif b == "2" and alist_2br.get(mkt_key):
                rent = alist_2br[mkt_key]
                source = "apartment_list"
            elif b == "3" and zillow_avg:
                # 3BR typically runs ~18% above blended market index
                rent = round(zillow_avg * 1.18, 2)
                source = "zillow_derived"
            elif b == "4" and zillow_avg:
                # 4BR typically runs ~35% above blended market index
                rent = round(zillow_avg * 1.35, 2)
                source = "zillow_derived"

            bedrooms[b] = {
                "averageRent": rent,
                "source": source,
            }

        supp["markets"][mkt_key] = {
            "zillow_avg": zillow_avg,
            "zillow_source": "zip+city_blend" if (z_zip and z_city) else ("zip" if z_zip else "city"),
            "bedrooms": bedrooms,
        }
        print(f"  {mkt_key}: Zillow ${zillow_avg or '—'} | "
              f"1BR ${alist_1br.get(mkt_key, '—')} | "
              f"2BR ${alist_2br.get(mkt_key, '—')}")

    return supp


def main():
    print(f"\n{'='*55}")
    print("Supplemental Data Fetch — Apartment List + Zillow")
    print(f"{'='*55}\n")

    all_zips = set()
    for mkt in MARKETS.values():
        all_zips.update(mkt["zips"])

    # ── Apartment List ─────────────────────────────────────────────────────
    print("Fetching Apartment List data...")
    alist_1br_rows = fetch_csv(ALIST_URLS["1"], "Apartment List 1BR")
    time.sleep(1)
    alist_2br_rows = fetch_csv(ALIST_URLS["2"], "Apartment List 2BR")

    alist_1br = parse_apartment_list(alist_1br_rows, "1") if alist_1br_rows else {}
    alist_2br = parse_apartment_list(alist_2br_rows, "2") if alist_2br_rows else {}
    print(f"  Matched markets — 1BR: {len(alist_1br)}, 2BR: {len(alist_2br)}")

    # ── Zillow Research ────────────────────────────────────────────────────
    print("\nFetching Zillow Research data...")
    time.sleep(1)
    zillow_city_rows = fetch_csv(ZILLOW_CITY_URL, "Zillow city ZORI")
    time.sleep(1)
    zillow_zip_rows  = fetch_csv(ZILLOW_URLS["all"], "Zillow zip ZORI")

    zillow_city = parse_zillow_city(zillow_city_rows) if zillow_city_rows else {}
    zillow_zip_raw = parse_zillow_zip(zillow_zip_rows, all_zips) if zillow_zip_rows else {}
    zillow_zip = aggregate_zips_to_market(zillow_zip_raw)
    print(f"  Matched markets — city: {len(zillow_city)}, zip: {len(zillow_zip)}")

    # ── Merge & save ───────────────────────────────────────────────────────
    print("\nBuilding supplemental market data...")
    supp = build_supplemental(alist_1br, alist_2br, zillow_city, zillow_zip)

    SUPP_FILE.parent.mkdir(parents=True, exist_ok=True)
    SUPP_FILE.write_text(json.dumps(supp, indent=2))
    print(f"\n✅ Supplemental data saved → {SUPP_FILE.name}")

    matched = sum(
        1 for m in supp["markets"].values()
        if any(b["averageRent"] for b in m["bedrooms"].values())
    )
    print(f"   Markets with at least one bedroom data point: {matched}/{len(MARKETS)}\n")


if __name__ == "__main__":
    main()
