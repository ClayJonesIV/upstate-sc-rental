# config.py — all market definitions, zip codes, and settings
# Edit this file to add/remove markets or zip codes

MARKETS = {
    "greenville": {
        "name": "Greenville",
        "label": "Greenville-Anderson-Mauldin MSA",
        "color": "#86b96e",
        "tier": "primary",
        "zips": ["29601", "29607", "29609", "29615"],
    },
    "spartanburg": {
        "name": "Spartanburg",
        "label": "Spartanburg MSA",
        "color": "#7eb3d4",
        "tier": "primary",
        "zips": ["29301", "29303", "29306"],
    },
    "anderson": {
        "name": "Anderson",
        "label": "Anderson, SC",
        "color": "#c4a36e",
        "tier": "primary",
        "zips": ["29621", "29624"],
    },
    "simpsonville": {
        "name": "Simpsonville",
        "label": "Simpsonville, SC",
        "color": "#b99ddb",
        "tier": "primary",
        "zips": ["29680", "29681"],
    },
    "greer": {
        "name": "Greer",
        "label": "Greer, SC",
        "color": "#5dbcb0",
        "tier": "primary",
        "zips": ["29650", "29651"],
    },
    "easley": {
        "name": "Easley",
        "label": "Easley, SC",
        "color": "#e07a6a",
        "tier": "foothills",
        "zips": ["29640", "29642"],
    },
    "piedmont": {
        "name": "Piedmont",
        "label": "Piedmont, SC",
        "color": "#d4845a",
        "tier": "foothills",
        "zips": ["29673"],
    },
    "liberty": {
        "name": "Liberty",
        "label": "Liberty, SC",
        "color": "#aacf6a",
        "tier": "foothills",
        "zips": ["29657"],
    },
    "clemson": {
        "name": "Clemson",
        "label": "Clemson, SC (college market)",
        "color": "#f4a235",
        "tier": "foothills",
        "zips": ["29631"],
        "notes": "College market — high seasonal vacancy May–Aug",
    },
    "seneca": {
        "name": "Seneca",
        "label": "Seneca / Lake Keowee, SC",
        "color": "#7ab8f5",
        "tier": "foothills",
        "zips": ["29678", "29672"],
        "notes": "29672 covers Lake Hartwell/Keowee Key lake communities",
    },
}

# All unique zip codes across all markets
ALL_ZIPS = []
ZIP_TO_MARKET = {}
for mkt_key, mkt in MARKETS.items():
    for z in mkt["zips"]:
        if z not in ALL_ZIPS:
            ALL_ZIPS.append(z)
        ZIP_TO_MARKET[z] = mkt_key

RENTCAST_BASE_URL = "https://api.rentcast.io/v1"

# Trend windows
MOM_MONTHS = 1
QOQ_MONTHS = 3
YOY_MONTHS = 12

# Metrics tracked per zip per month
TRACKED_METRICS = [
    "averageRent",
    "medianRent",
    "averageDaysOnMarket",
    "medianDaysOnMarket",
    "totalListings",
    "newListings",
]

# Bedroom breakdowns tracked
BEDROOM_SIZES = [1, 2, 3, 4]
