#!/usr/bin/env python3
"""
fetch_data.py
Calls RentCast /markets for every configured zip code, merges results by market,
blends in supplemental bedroom data, writes the latest month to history.json,
and records a zip-level DOM audit trail for future diagnostics.

Key DOM rules:
  - Average days on market is listing-weighted across ZIPs
  - Historical DOM backfill comes from RentCast embedded month history
  - The DOM audit log is the authoritative source for future comparisons
"""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import ALL_ZIPS, MARKETS, RENTCAST_BASE_URL, BEDROOM_SIZES

HISTORY_FILE = Path(__file__).parent.parent / "data" / "history.json"
RAW_FILE = Path(__file__).parent.parent / "data" / "raw_latest.json"
SUPP_FILE = Path(__file__).parent.parent / "data" / "supplemental_latest.json"
DOM_AUDIT_FILE = Path(__file__).parent.parent / "data" / "rentcast_dom_audit.json"

MAX_API_CALLS = 50
HISTORY_MONTHS = 15
_call_count = 0


def build_headers() -> dict:
    return {
        "X-Api-Key": os.environ["RENTCAST_API_KEY"],
        "Accept": "application/json",
    }


def weighted_average(pairs: list[tuple[float, float]]) -> float | None:
    usable = [(value, weight) for value, weight in pairs if value is not None and weight is not None and weight > 0]
    if not usable:
        return None
    total_weight = sum(weight for _, weight in usable)
    if total_weight == 0:
        return None
    return round(sum(value * weight for value, weight in usable) / total_weight, 2)


def fetch_zip(zip_code: str) -> dict | None:
    global _call_count
    if _call_count >= MAX_API_CALLS:
        print(f"  Skipping {zip_code} - API call limit of {MAX_API_CALLS} reached")
        return None

    url = f"{RENTCAST_BASE_URL}/markets"
    params = {"zipCode": zip_code, "historyMonths": HISTORY_MONTHS}
    try:
        response = requests.get(url, headers=build_headers(), params=params, timeout=30)
        response.raise_for_status()
        _call_count += 1
        print(f"  OK {zip_code} (call {_call_count}/{MAX_API_CALLS})")
        return response.json()
    except requests.HTTPError:
        print(f"  ERR {zip_code} - HTTP {response.status_code}: {response.text[:120]}")
        return None
    except Exception as exc:
        print(f"  ERR {zip_code} - {exc}")
        return None


def extract_rental_metrics(data: dict, bedrooms: int | None = None) -> dict:
    rental = data.get("rentalData", {})
    if bedrooms is not None:
        key = f"{bedrooms}bedroom"
        bedroom_data = rental.get("bedrooms", {}).get(key, {})
        return {
            "averageRent": bedroom_data.get("averageRent"),
            "medianRent": bedroom_data.get("medianRent"),
            "averageDaysOnMarket": bedroom_data.get("averageDaysOnMarket"),
            "medianDaysOnMarket": bedroom_data.get("medianDaysOnMarket"),
            "totalListings": bedroom_data.get("totalListings"),
            "newListings": bedroom_data.get("newListings"),
        }
    return {
        "averageRent": rental.get("averageRent"),
        "medianRent": rental.get("medianRent"),
        "averageDaysOnMarket": rental.get("averageDaysOnMarket"),
        "medianDaysOnMarket": rental.get("medianDaysOnMarket"),
        "totalListings": rental.get("totalListings"),
        "newListings": rental.get("newListings"),
    }


def merge_zips_for_market(zip_results: list[dict]) -> dict:
    """
    Aggregate ZIP-level metrics to the market level.

    DOM uses listing-weighted averaging so larger ZIP inventories carry more influence.
    Other fields preserve the prior averaging behavior for continuity.
    """
    merged = {}
    metric_keys = [
        "averageRent",
        "medianRent",
        "averageDaysOnMarket",
        "medianDaysOnMarket",
        "totalListings",
        "newListings",
    ]

    for key in metric_keys:
        if key == "averageDaysOnMarket":
            merged[key] = weighted_average([
                (row.get("averageDaysOnMarket"), row.get("totalListings"))
                for row in zip_results
            ])
        else:
            vals = [row[key] for row in zip_results if row.get(key) is not None]
            merged[key] = round(sum(vals) / len(vals), 2) if vals else None

    merged["bedrooms"] = {}
    for bedroom in BEDROOM_SIZES:
        bkey = str(bedroom)
        rent_vals = []
        listing_vals = []
        dom_pairs = []
        for row in zip_results:
            bd = row.get("bedrooms", {}).get(bkey, {})
            if bd.get("averageRent") is not None:
                rent_vals.append(bd["averageRent"])
            if bd.get("averageDaysOnMarket") is not None and bd.get("totalListings") is not None:
                dom_pairs.append((bd["averageDaysOnMarket"], bd["totalListings"]))
            if bd.get("totalListings") is not None:
                listing_vals.append(bd["totalListings"])
        merged["bedrooms"][bkey] = {
            "averageRent_rentcast": round(sum(rent_vals) / len(rent_vals), 2) if rent_vals else None,
            "averageDaysOnMarket": weighted_average(dom_pairs),
            "totalListings": sum(listing_vals) if listing_vals else None,
        }

    return merged


def blend_supplemental(market_data: dict, supp_market: dict | None) -> dict:
    if not supp_market:
        for bkey in market_data.get("bedrooms", {}):
            bd = market_data["bedrooms"][bkey]
            bd["averageRent"] = bd.pop("averageRent_rentcast", None)
            bd["rent_source"] = "rentcast"
        return market_data

    for bkey in market_data.get("bedrooms", {}):
        bd = market_data["bedrooms"][bkey]
        rc_rent = bd.pop("averageRent_rentcast", None)
        supp_bd = supp_market.get("bedrooms", {}).get(bkey, {})
        supp_rent = supp_bd.get("averageRent")
        source = supp_bd.get("source", "unknown")

        if supp_rent:
            bd["averageRent"] = supp_rent
            bd["rent_source"] = source
        elif rc_rent:
            bd["averageRent"] = rc_rent
            bd["rent_source"] = "rentcast"
        else:
            bd["averageRent"] = None
            bd["rent_source"] = "unavailable"

    market_data["zillow_avg"] = supp_market.get("zillow_avg")
    return market_data


def extract_monthly_dom_metrics(raw: dict, month: str) -> dict:
    rental = raw.get("rentalData", {})
    current_month = (rental.get("lastUpdatedDate") or "")[:7]
    if month == current_month:
        source = rental
        source_date = rental.get("lastUpdatedDate")
    else:
        source = rental.get("history", {}).get(month, {})
        source_date = source.get("date")
    return {
        "date": source_date,
        "averageDaysOnMarket": source.get("averageDaysOnMarket"),
        "totalListings": source.get("totalListings"),
    }


def build_dom_audit(all_zip_data: dict, run_date: datetime) -> dict:
    months = set()
    for raw in all_zip_data.values():
        rental = raw.get("rentalData", {})
        months.update(rental.get("history", {}).keys())
        current_month = (rental.get("lastUpdatedDate") or "")[:7]
        if current_month:
            months.add(current_month)

    audit = {
        "generated_at": run_date.isoformat(),
        "markets": {},
    }

    for market_key, market_cfg in MARKETS.items():
        month_map = {}
        for month in sorted(months):
            zip_rows = []
            for zip_code in market_cfg["zips"]:
                raw = all_zip_data.get(zip_code)
                if raw is None:
                    continue
                metrics = extract_monthly_dom_metrics(raw, month)
                if metrics["averageDaysOnMarket"] is None and metrics["totalListings"] is None:
                    continue
                zip_rows.append({
                    "zip_code": zip_code,
                    "date": metrics["date"],
                    "averageDaysOnMarket": metrics["averageDaysOnMarket"],
                    "totalListings": metrics["totalListings"],
                })

            if not zip_rows:
                continue

            weighted_dom = weighted_average([
                (row["averageDaysOnMarket"], row["totalListings"])
                for row in zip_rows
            ])
            simple_vals = [row["averageDaysOnMarket"] for row in zip_rows if row["averageDaysOnMarket"] is not None]
            month_map[month] = {
                "weighted_averageDaysOnMarket": weighted_dom,
                "simple_averageDaysOnMarket": round(sum(simple_vals) / len(simple_vals), 2) if simple_vals else None,
                "totalListings_sum": sum(row["totalListings"] for row in zip_rows if row["totalListings"] is not None),
                "zip_count": len(zip_rows),
                "zips": zip_rows,
            }

        audit["markets"][market_key] = {"months": month_map}

    return audit


def save_dom_audit(audit: dict):
    DOM_AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    DOM_AUDIT_FILE.write_text(json.dumps(audit, indent=2))


def backfill_history_dom_from_audit(history: list, audit: dict) -> list:
    for record in history:
        month = record.get("month")
        if not month:
            continue
        for market_key in MARKETS:
            mkt_record = record.get("markets", {}).get(market_key)
            if not mkt_record:
                continue
            audit_month = (
                audit.get("markets", {})
                .get(market_key, {})
                .get("months", {})
                .get(month)
            )
            if not audit_month:
                continue
            dom_value = audit_month.get("weighted_averageDaysOnMarket")
            if dom_value is not None:
                mkt_record["averageDaysOnMarket"] = dom_value
    return history


def build_month_record(run_date: datetime, all_zip_data: dict, supplemental: dict | None) -> dict:
    record = {
        "month": run_date.strftime("%Y-%m"),
        "fetched_at": run_date.isoformat(),
        "data_sources": ["rentcast"],
        "markets": {},
    }

    if supplemental:
        for source in supplemental.get("sources", []):
            if source not in record["data_sources"]:
                record["data_sources"].append(source)

    for market_key, market_cfg in MARKETS.items():
        zip_results = []
        for zip_code in market_cfg["zips"]:
            raw = all_zip_data.get(zip_code)
            if raw is None:
                continue
            agg = extract_rental_metrics(raw)
            agg["bedrooms"] = {}
            for bedroom in BEDROOM_SIZES:
                agg["bedrooms"][str(bedroom)] = extract_rental_metrics(raw, bedrooms=bedroom)
            zip_results.append(agg)

        if not zip_results:
            print(f"  WARN {market_key}: no RentCast data from any zip")
            record["markets"][market_key] = None
            continue

        merged = merge_zips_for_market(zip_results)
        supp_market = supplemental.get("markets", {}).get(market_key) if supplemental else None
        blended = blend_supplemental(merged, supp_market)
        record["markets"][market_key] = blended

        filled = sum(1 for b in ["1", "2", "3", "4"] if blended["bedrooms"].get(b, {}).get("averageRent"))
        sources_used = set(
            blended["bedrooms"].get(b, {}).get("rent_source", "")
            for b in ["1", "2", "3", "4"]
        ) - {"unavailable", ""}
        print(
            f"  OK {market_key}: merged {len(zip_results)} zip(s), "
            f"{filled}/4 bedroom sizes filled [{', '.join(sorted(sources_used))}]"
        )

    return record


def load_history() -> list:
    if HISTORY_FILE.exists():
        history = json.loads(HISTORY_FILE.read_text())
        history.sort(key=lambda record: record.get("month", ""))
        return history
    return []


def save_history(history: list):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    history.sort(key=lambda record: record.get("month", ""))
    HISTORY_FILE.write_text(json.dumps(history, indent=2))


def load_cached_rentcast() -> dict:
    if not RAW_FILE.exists():
        raise FileNotFoundError(
            f"{RAW_FILE.name} not found. Run a full fetch first before using --skip-rentcast."
        )
    return json.loads(RAW_FILE.read_text())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-rentcast",
        action="store_true",
        help="Reuse data/raw_latest.json instead of making fresh RentCast API calls.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    run_date = datetime.now(timezone.utc)
    current_month = run_date.strftime("%Y-%m")
    print(f"\n{'=' * 55}")
    print(f"RentCast Fetch - {run_date.strftime('%B %Y')}")
    print(f"{'=' * 55}")

    supplemental = None
    if SUPP_FILE.exists():
        supplemental = json.loads(SUPP_FILE.read_text())
        supp_month = supplemental.get("month", "")
        if supp_month == current_month:
            print(f"\nOK Supplemental data loaded ({supp_month}) - sources: {', '.join(supplemental.get('sources', []))}")
        else:
            print(f"\nWARN Supplemental data is from {supp_month}, not {current_month} - using anyway")
    else:
        print("\nWARN No supplemental data found - bedroom rents will be RentCast-only")

    if args.skip_rentcast:
        print(f"\nSkipping fresh RentCast calls and reusing {RAW_FILE.name}...")
        all_zip_data = load_cached_rentcast()
        print(f"Loaded cached RentCast data for {len(all_zip_data)}/{len(ALL_ZIPS)} zips")
    else:
        print(f"\nFetching {len(ALL_ZIPS)} zip codes from RentCast...")
        all_zip_data = {}
        for index, zip_code in enumerate(ALL_ZIPS):
            result = fetch_zip(zip_code)
            if result:
                all_zip_data[zip_code] = result
            if index < len(ALL_ZIPS) - 1:
                time.sleep(0.5)

        RAW_FILE.parent.mkdir(parents=True, exist_ok=True)
        RAW_FILE.write_text(json.dumps(all_zip_data, indent=2))
        print(f"\nRaw RentCast data saved -> {RAW_FILE.name}")

    print("\nMerging by market + blending supplemental data...")
    month_record = build_month_record(run_date, all_zip_data, supplemental)
    dom_audit = build_dom_audit(all_zip_data, run_date)
    save_dom_audit(dom_audit)
    print(f"DOM audit saved -> {DOM_AUDIT_FILE.name}")

    history = load_history()
    existing = [i for i, record in enumerate(history) if record.get("month") == current_month]
    if existing:
        history[existing[0]] = month_record
        print(f"\nReplaced existing record for {current_month}")
    else:
        history.append(month_record)
        print(f"\nAppended new record for {current_month} ({len(history)} months total)")

    history = backfill_history_dom_from_audit(history, dom_audit)
    history.sort(key=lambda record: record.get("month", ""))
    save_history(history)
    print(f"History saved -> {HISTORY_FILE.name}")
    print(f"\nOK Fetch complete")
    print(f"   RentCast zips: {len(all_zip_data)}/{len(ALL_ZIPS)}")
    print(f"   API calls used: {_call_count}/{MAX_API_CALLS}")
    print(f"   Mode: {'cached RentCast reuse' if args.skip_rentcast else 'live RentCast fetch'}")
    print(f"   Data sources: {', '.join(month_record.get('data_sources', ['rentcast']))}\n")


if __name__ == "__main__":
    main()
