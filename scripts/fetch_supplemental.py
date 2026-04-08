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
import argparse
import json
import io
import re
import time
import requests
from pathlib import Path
from datetime import datetime, timezone
import sys

sys.path.insert(0, str(Path(__file__).parent))
from config import MARKETS

SUPP_FILE = Path(__file__).parent.parent / "data" / "supplemental_latest.json"

# ── Apartment List sources ─────────────────────────────────────────────────────
ALIST_DATA_PAGE = "https://www.apartmentlist.com/research/category/data-rent-estimates"

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

APARTMENT_LIST_FALLBACKS = {
    "greenville":  ["Greenville, SC", "Greenville County, SC", "Greenville-Anderson, SC"],
    "spartanburg": ["Spartanburg, SC", "Spartanburg County, SC"],
    "anderson":    ["Greenville-Anderson, SC"],
    "simpsonville":["Greenville-Anderson, SC", "Greenville County, SC"],
    "greer":       ["Greenville-Anderson, SC", "Greenville County, SC"],
    "easley":      ["Greenville-Anderson, SC", "Greenville County, SC"],
    "piedmont":    ["Greenville-Anderson, SC"],
    "liberty":     ["Greenville-Anderson, SC"],
    "clemson":     ["Greenville-Anderson, SC"],
    "seneca":      [],
}


def fetch_csv(url: str, label: str) -> list[dict] | None:
    """Download a CSV URL and return list of row dicts."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        reader = csv.DictReader(io.StringIO(r.text))
        rows = list(reader)
        print(f"  OK {label}: {len(rows):,} rows")
        return rows
    except Exception as e:
        print(f"  ERROR {label}: {e}")
        return None


def load_previous_apartment_list() -> tuple[dict, dict]:
    """Reuse prior 1BR/2BR Apartment List values when the live endpoint is unavailable."""
    if not SUPP_FILE.exists():
        return {}, {}

    try:
        existing = json.loads(SUPP_FILE.read_text())
    except Exception as e:
        print(f"  WARN Could not read existing supplemental file: {e}")
        return {}, {}

    alist_1br = {}
    alist_2br = {}
    for mkt_key, market_data in existing.get("markets", {}).items():
        beds = market_data.get("bedrooms", {})
        bd1 = beds.get("1", {})
        bd2 = beds.get("2", {})
        if bd1.get("source") == "apartment_list" and bd1.get("averageRent") is not None:
            alist_1br[mkt_key] = {
                "averageRent": bd1["averageRent"],
                "source_detail": bd1.get("source_detail"),
            }
        if bd2.get("source") == "apartment_list" and bd2.get("averageRent") is not None:
            alist_2br[mkt_key] = {
                "averageRent": bd2["averageRent"],
                "source_detail": bd2.get("source_detail"),
            }

    return alist_1br, alist_2br


def fetch_apartment_list_summary_rows() -> list[dict] | None:
    """Discover the current Apartment List summary CSV from the data page and download it."""
    try:
        page = requests.get(ALIST_DATA_PAGE, headers=HEADERS, timeout=TIMEOUT)
        page.raise_for_status()
        match = re.search(
            r'"label":"Current Month Summary","url":"(?P<url>//assets\.ctfassets\.net/[^"]+Apartment_List_Rent_Estimates_Summary_[^"]+\.csv)"',
            page.text,
        )
        if not match:
            print("  ERROR Apartment List summary URL not found on data page")
            return None

        url = "https:" + match.group("url")
        return fetch_csv(url, "Apartment List current summary")
    except Exception as e:
        print(f"  ERROR Apartment List discovery failed: {e}")
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-apartment-list-live",
        action="store_true",
        help="Exit non-zero if live Apartment List 1BR/2BR data could not be fetched.",
    )
    return parser.parse_args()


def latest_month_col(headers: list[str]) -> str | None:
    """Find the most recent YYYY-MM date column in a Zillow CSV."""
    date_cols = [h for h in headers if len(h) == 10 and h[4] == "-" and h[7] == "-"]
    if not date_cols:
        return None
    return sorted(date_cols)[-1]


def parse_apartment_list(rows: list[dict], bedroom: str) -> dict:
    """
    Extract latest rent per market from Apartment List current summary CSV.
    Returns {market_key: rent_float}
    """
    price_col = f"price_{bedroom}br"
    if not rows or price_col not in rows[0]:
        return {}

    lookup = {}
    for row in rows:
        location_name = row.get("location_name", "").strip()
        val = row.get(price_col, "")
        try:
            rent = float(val)
            lookup[location_name] = {
                "averageRent": rent,
                "source_detail": location_name,
            }
        except (ValueError, AttributeError):
            pass

    result = {}
    for mkt_key, fallback_names in APARTMENT_LIST_FALLBACKS.items():
        for location_name in fallback_names:
            rent = lookup.get(location_name)
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
            detail = row.get("location_name", "").strip() if row.get("location_name") else ""
            metro = row.get("Metro", "").strip()
            location_label = f"{city}, {state}" if city and state else city
            lookup[(city.lower(), state)] = {
                "averageRent": rent,
                "source_detail": metro or location_label,
            }
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
            result[mkt_key] = {
                "averageRent": round(sum(vals) / len(vals), 2),
                "source_detail": f"zip-level average across {', '.join(mkt_cfg['zips'])}",
            }
    return result


def build_supplemental(
    alist_1br: dict,
    alist_2br: dict,
    zillow_city: dict,
    zillow_zip: dict,
    source_flags: dict | None = None,
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
        "source_status": source_flags or {},
        "markets": {},
    }

    for mkt_key in MARKETS:
        z_city = zillow_city.get(mkt_key)
        z_zip  = zillow_zip.get(mkt_key)
        z_city_val = z_city.get("averageRent") if z_city else None
        z_zip_val = z_zip.get("averageRent") if z_zip else None

        # Blend Zillow signals for overall avg (prefer zip-level when available)
        zillow_avg = None
        if z_zip_val and z_city_val:
            zillow_avg = round((z_zip_val * 0.6 + z_city_val * 0.4), 2)
        elif z_zip_val:
            zillow_avg = z_zip_val
        elif z_city_val:
            zillow_avg = z_city_val

        # Per-bedroom estimates
        bedrooms = {}
        for b in ["1", "2", "3", "4"]:
            rent = None
            source = None
            source_detail = None
            if b == "1" and alist_1br.get(mkt_key):
                rent = alist_1br[mkt_key]["averageRent"]
                source = "apartment_list"
                source_detail = alist_1br[mkt_key].get("source_detail")
            elif b == "2" and alist_2br.get(mkt_key):
                rent = alist_2br[mkt_key]["averageRent"]
                source = "apartment_list"
                source_detail = alist_2br[mkt_key].get("source_detail")
            elif b == "3" and zillow_avg:
                # 3BR typically runs ~18% above blended market index
                rent = round(zillow_avg * 1.18, 2)
                source = "zillow_derived"
                source_detail = (
                    z_city.get("source_detail") if z_city else z_zip.get("source_detail") if z_zip else None
                )
            elif b == "4" and zillow_avg:
                # 4BR typically runs ~35% above blended market index
                rent = round(zillow_avg * 1.35, 2)
                source = "zillow_derived"
                source_detail = (
                    z_city.get("source_detail") if z_city else z_zip.get("source_detail") if z_zip else None
                )

            bedrooms[b] = {
                "averageRent": rent,
                "source": source,
                "source_detail": source_detail,
            }

        supp["markets"][mkt_key] = {
            "zillow_avg": zillow_avg,
            "zillow_source": "zip+city_blend" if (z_zip_val and z_city_val) else ("zip" if z_zip_val else "city"),
            "zillow_source_detail": (
                f"{z_zip.get('source_detail')} + {z_city.get('source_detail')}"
                if (z_zip_val and z_city_val)
                else (z_zip.get("source_detail") if z_zip_val else z_city.get("source_detail") if z_city_val else None)
            ),
            "bedrooms": bedrooms,
        }
        print(f"  {mkt_key}: Zillow ${zillow_avg or 'n/a'} | "
              f"1BR ${alist_1br.get(mkt_key, {}).get('averageRent', 'n/a')} | "
              f"2BR ${alist_2br.get(mkt_key, {}).get('averageRent', 'n/a')}")

    return supp


def main():
    args = parse_args()
    print(f"\n{'='*55}")
    print("Supplemental Data Fetch — Apartment List + Zillow")
    print(f"{'='*55}\n")

    all_zips = set()
    for mkt in MARKETS.values():
        all_zips.update(mkt["zips"])

    # ── Apartment List ─────────────────────────────────────────────────────
    print("Fetching Apartment List data...")
    alist_rows = fetch_apartment_list_summary_rows()

    alist_1br = parse_apartment_list(alist_rows, "1") if alist_rows else {}
    alist_2br = parse_apartment_list(alist_rows, "2") if alist_rows else {}
    if not alist_rows:
        prev_1br, prev_2br = load_previous_apartment_list()
        if prev_1br or prev_2br:
            print("  WARN Apartment List fetch failed; reusing prior saved 1BR/2BR values")
            if not alist_1br:
                alist_1br = prev_1br
            if not alist_2br:
                alist_2br = prev_2br
        else:
            print("  WARN Apartment List fetch failed and no prior saved values were found")
    print(f"  Matched markets - 1BR: {len(alist_1br)}, 2BR: {len(alist_2br)}")
    if args.require_apartment_list_live and not alist_rows:
        raise SystemExit("Apartment List live fetch check failed")

    # ── Zillow Research ────────────────────────────────────────────────────
    print("\nFetching Zillow Research data...")
    time.sleep(1)
    zillow_city_rows = fetch_csv(ZILLOW_CITY_URL, "Zillow city ZORI")
    time.sleep(1)
    zillow_zip_rows  = fetch_csv(ZILLOW_URLS["all"], "Zillow zip ZORI")

    zillow_city = parse_zillow_city(zillow_city_rows) if zillow_city_rows else {}
    zillow_zip_raw = parse_zillow_zip(zillow_zip_rows, all_zips) if zillow_zip_rows else {}
    zillow_zip = aggregate_zips_to_market(zillow_zip_raw)
    print(f"  Matched markets - city: {len(zillow_city)}, zip: {len(zillow_zip)}")

    # ── Merge & save ───────────────────────────────────────────────────────
    print("\nBuilding supplemental market data...")
    supp = build_supplemental(
        alist_1br,
        alist_2br,
        zillow_city,
        zillow_zip,
        source_flags={
            "apartment_list_live": bool(alist_rows),
            "zillow_live": bool(zillow_city_rows and zillow_zip_rows),
        },
    )

    SUPP_FILE.parent.mkdir(parents=True, exist_ok=True)
    SUPP_FILE.write_text(json.dumps(supp, indent=2))
    print(f"\nOK Supplemental data saved -> {SUPP_FILE.name}")

    matched = sum(
        1 for m in supp["markets"].values()
        if any(b["averageRent"] for b in m["bedrooms"].values())
    )
    print(f"   Markets with at least one bedroom data point: {matched}/{len(MARKETS)}\n")


if __name__ == "__main__":
    main()
