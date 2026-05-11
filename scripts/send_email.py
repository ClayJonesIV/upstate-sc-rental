#!/usr/bin/env python3
"""
send_email.py
Sends the grouped HTML email report via Gmail SMTP.
"""

import json
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

TRENDS_FILE = Path(__file__).parent.parent / "data" / "trends.json"
INSIGHTS_FILE = Path(__file__).parent.parent / "data" / "insights.json"

import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import MARKETS

GROUPS = {
    "headline": {
        "title": "Upstate Headline",
        "markets": list(MARKETS.keys()),
        "description": "High-level regional read across all tracked Upstate markets.",
    },
    "greenville": {
        "title": "Greenville",
        "markets": ["greenville"],
        "description": "Highest-confidence core market view with the cleanest direct source coverage.",
    },
    "spartanburg": {
        "title": "Spartanburg",
        "markets": ["spartanburg"],
        "description": "High-confidence market view with steadier inventory depth and direct source coverage.",
    },
    "other": {
        "title": "Other Markets",
        "markets": ["anderson", "simpsonville", "greer", "easley", "piedmont", "clemson", "seneca"],
        "description": "Directional view for Anderson, Simpsonville, Greer, Easley, Piedmont, Clemson, and Seneca.",
    },
}

GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PW = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENT = os.environ["REPORT_RECIPIENT"]
PAGES_URL = os.environ.get("PAGE_URL") or os.environ.get("GITHUB_PAGES_URL", "https://your-username.github.io/upstate-sc-rental")


def fmt_rent(value):
    return "-" if value is None else f"${value:,.0f}"


def fmt_pct(value):
    if value is None:
        return "-"
    return f"{'+' if value > 0 else ''}{value:.1f}%"


def fmt_days(value):
    return "-" if value is None else f"{value:.0f}d"


def pct_color(value):
    if value is None:
        return "#6b716c"
    return "#2f355d" if value >= 0 else "#fd5315"


def temp_color(temp):
    return {
        "hot": "#e07a6a",
        "warm": "#f4a235",
        "neutral": "#2f355d",
        "cool": "#5d729a",
        "cold": "#8b84b2",
    }.get(temp, "#2f355d")


def insight_html(text, color="#2f355d", headers=None):
    headers = headers or [
        "MARKET CONDITIONS",
        "IMPLICATIONS FOR CURRENT OWNERS",
        "VACANCY MARKETING STRATEGY",
        "RENEWAL PRICING STRATEGY",
        "UPSTATE SC MACRO VIEW",
        "OUTLOOK AND RISKS",
    ]
    html = (text or "Analysis not available.").replace("**", "")
    for header in headers:
        html = html.replace(
            header,
            f'<div style="font-size:10px;color:{color};letter-spacing:1.5px;text-transform:uppercase;font-family:Montserrat,sans-serif;margin:16px 0 6px;font-weight:700">{header}</div>',
        )

    blocks = []
    for chunk in html.split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.startswith("<div"):
            blocks.append(chunk)
        else:
            blocks.append(f'<p style="font-size:13px;color:#2d2e30;line-height:1.7;margin:0 0 12px">{chunk}</p>')
    return "".join(blocks)


def aggregate_group_metrics(group_keys, trends):
    rent_vals, dom_vals, listing_vals = [], [], []
    weighted_rent_mom, weighted_dom_mom = [], []
    temps = []
    for key in group_keys:
        market = trends.get("markets", {}).get(key, {})
        agg = market.get("aggregate", {})
        weight = agg.get("totalListings", {}).get("current") or 1
        rent = agg.get("averageRent", {}).get("current")
        dom = agg.get("averageDaysOnMarket", {}).get("current")
        listings = agg.get("totalListings", {}).get("current")
        mom = agg.get("averageRent", {}).get("changes", {}).get("mom", {}).get("pct_change")
        dom_mom = agg.get("averageDaysOnMarket", {}).get("changes", {}).get("mom", {}).get("pct_change")
        if rent is not None:
            rent_vals.append((rent, weight))
        if dom is not None:
            dom_vals.append((dom, weight))
        if listings is not None:
            listing_vals.append(listings)
        if mom is not None:
            weighted_rent_mom.append((mom, weight))
        if dom_mom is not None:
            weighted_dom_mom.append((dom_mom, weight))
        temp = market.get("market_conditions", {}).get("temperature")
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
        "average_rent": round(sum(v * w for v, w in rent_vals) / sum(w for _, w in rent_vals), 2) if rent_vals else None,
        "average_dom": round(sum(v * w for v, w in dom_vals) / sum(w for _, w in dom_vals), 2) if dom_vals else None,
        "total_listings": round(sum(listing_vals), 2) if listing_vals else None,
        "average_mom": round(sum(v * w for v, w in weighted_rent_mom) / sum(w for _, w in weighted_rent_mom), 2) if weighted_rent_mom else None,
        "average_dom_mom": round(sum(v * w for v, w in weighted_dom_mom) / sum(w for _, w in weighted_dom_mom), 2) if weighted_dom_mom else None,
        "temperature": temp,
        "temperature_label": temp_label,
    }


def build_other_markets_rows(trends):
    rows = []
    for key in GROUPS["other"]["markets"]:
        market = trends.get("markets", {}).get(key, {})
        agg = market.get("aggregate", {})
        cond = market.get("market_conditions", {})
        mom = agg.get("averageRent", {}).get("changes", {}).get("mom", {}).get("pct_change")
        tc = temp_color(cond.get("temperature"))
        rows.append(
            f"""
            <tr>
              <td style="padding:12px 14px;border-bottom:1px solid #d9ded7;font-weight:700;color:{MARKETS[key]['color']};white-space:nowrap">{MARKETS[key]['name']}</td>
              <td style="padding:12px 14px;border-bottom:1px solid #d9ded7;font-size:16px;font-weight:800;color:#2d2e30;white-space:nowrap">{fmt_rent(agg.get('averageRent', {}).get('current'))}</td>
              <td style="padding:12px 14px;border-bottom:1px solid #d9ded7;color:{pct_color(mom)};font-weight:700;white-space:nowrap">{fmt_pct(mom)}</td>
              <td style="padding:12px 14px;border-bottom:1px solid #d9ded7"><span style="background:{tc}22;color:{tc};border:1px solid {tc}55;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;white-space:nowrap">{cond.get('temperature_label', '-')}</span></td>
            </tr>"""
        )
    return "".join(rows)


def build_group_section(group_key, trends, insights):
    group = GROUPS[group_key]
    metrics = aggregate_group_metrics(group["markets"], trends)
    color = "#2f355d" if group_key == "headline" else MARKETS[group["markets"][0]]["color"]
    tc = temp_color(metrics["temperature"])
    dom_trend_html = ""
    if group_key != "other":
        dom_trend_html = f"<div style='font-size:11px;color:{pct_color(-metrics['average_dom_mom'])};margin-top:4px'>MoM {fmt_pct(metrics['average_dom_mom'])}</div>" if metrics["average_dom_mom"] is not None else ""

    if group_key == "headline":
        body = f"""
        <div style="background:#fbfcfa;border:1px solid #d9ded7;border-radius:10px;padding:18px 20px;margin-top:16px">
          {insight_html(insights.get("regional", ""), color="#2f355d", headers=["UPSTATE SC MACRO VIEW", "OUTLOOK AND RISKS"])}
        </div>"""
    elif group_key in {"greenville", "spartanburg"}:
        market_key = group["markets"][0]
        body = f"""
        <div style="background:#fbfcfa;border:1px solid #d9ded7;border-radius:10px;padding:18px 20px;margin-top:16px">
          {insight_html(insights.get("markets", {}).get(market_key, ""), color=color, headers=["MARKET CONDITIONS", "IMPLICATIONS FOR CURRENT OWNERS", "VACANCY MARKETING STRATEGY", "RENEWAL PRICING STRATEGY"])}
        </div>"""
    else:
        body = f"""
        <div style="margin-top:16px;font-size:13px;color:#2d2e30;line-height:1.7">
          Directional read for Anderson, Simpsonville, Greer, Easley, Piedmont, Clemson, and Seneca.
          Smaller and more specialized markets should be read more cautiously than Greenville and Spartanburg.
        </div>
        <div style="overflow-x:auto;margin-top:16px">
          <table style="width:100%;border-collapse:collapse;background:#ffffff;border:1px solid #d9ded7;border-radius:10px;overflow:hidden">
            <thead>
              <tr style="background:#f7f7f3">
                <th style="padding:10px 14px;text-align:left;color:#6b716c;font-size:10px;letter-spacing:.5px;text-transform:uppercase;font-family:Montserrat,sans-serif">Market</th>
                <th style="padding:10px 14px;text-align:left;color:#6b716c;font-size:10px;letter-spacing:.5px;text-transform:uppercase">Avg Rent</th>
                <th style="padding:10px 14px;text-align:left;color:#6b716c;font-size:10px;letter-spacing:.5px;text-transform:uppercase">MoM</th>
                <th style="padding:10px 14px;text-align:left;color:#6b716c;font-size:10px;letter-spacing:.5px;text-transform:uppercase">Temp</th>
              </tr>
            </thead>
            <tbody>{build_other_markets_rows(trends)}</tbody>
          </table>
        </div>"""

    return f"""
    <div style="margin-bottom:34px;border-left:3px solid {color};padding-left:18px">
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:6px">
        <h3 style="color:{color};font-size:18px;font-weight:700;margin:0;font-family:Montserrat,sans-serif">{group['title']}</h3>
        <span style="background:{tc}22;color:{tc};border:1px solid {tc}55;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;white-space:nowrap">{metrics['temperature_label']}</span>
      </div>
      <div style="font-size:12px;color:#6b716c;line-height:1.6">{group['description']}</div>
      <div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:14px">
        <div style="background:#f7f7f3;border:1px solid #d9ded7;border-radius:10px;padding:12px 14px;min-width:150px">
          <div style="font-size:10px;color:#6b716c;text-transform:uppercase;letter-spacing:1px;font-family:Montserrat,sans-serif">Avg Rent</div>
          <div style="font-size:21px;font-weight:800;color:#2d2e30;font-family:Montserrat,sans-serif">{fmt_rent(metrics['average_rent'])}</div>
        </div>
        <div style="background:#f7f7f3;border:1px solid #d9ded7;border-radius:10px;padding:12px 14px;min-width:150px">
          <div style="font-size:10px;color:#6b716c;text-transform:uppercase;letter-spacing:1px;font-family:Montserrat,sans-serif">Avg MoM</div>
          <div style="font-size:21px;font-weight:800;color:{pct_color(metrics['average_mom'])};font-family:Montserrat,sans-serif">{fmt_pct(metrics['average_mom'])}</div>
        </div>
        <div style="background:#f7f7f3;border:1px solid #d9ded7;border-radius:10px;padding:12px 14px;min-width:150px">
          <div style="font-size:10px;color:#6b716c;text-transform:uppercase;letter-spacing:1px;font-family:Montserrat,sans-serif">Avg DOM</div>
          <div style="font-size:21px;font-weight:800;color:#2d2e30;font-family:Montserrat,sans-serif">{fmt_days(metrics['average_dom'])}</div>
          {dom_trend_html}
        </div>
        <div style="background:#f7f7f3;border:1px solid #d9ded7;border-radius:10px;padding:12px 14px;min-width:150px">
          <div style="font-size:10px;color:#6b716c;text-transform:uppercase;letter-spacing:1px;font-family:Montserrat,sans-serif">Listings</div>
          <div style="font-size:21px;font-weight:800;color:#2d2e30;font-family:Montserrat,sans-serif">{f"{metrics['total_listings']:,.0f}" if metrics['total_listings'] is not None else "-"}</div>
        </div>
      </div>
      {body}
    </div>"""


def build_email_html(trends, insights):
    as_of = trends.get("as_of", "")
    as_of_display = datetime.strptime(as_of, "%Y-%m").strftime("%B %Y") if as_of else "-"
    rs = trends.get("regional_summary", {})
    hottest = MARKETS.get(rs.get("hottest_market", ""), {}).get("name", "-")
    softest = MARKETS.get(rs.get("softest_market", ""), {}).get("name", "-")
    avg_mom_values = [
        trends["markets"][market]["aggregate"]["averageRent"]["changes"]["mom"]["pct_change"]
        for market in MARKETS
        if trends["markets"][market]["aggregate"]["averageRent"]["changes"]["mom"]["pct_change"] is not None
    ]
    avg_mom = round(sum(avg_mom_values) / len(avg_mom_values), 2) if avg_mom_values else None

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/></head>
<body style="background:#f7f7f3;color:#2d2e30;font-family:Roboto,sans-serif;margin:0;padding:0">
<div style="max-width:900px;margin:0 auto;padding:0 0 40px">
  <div style="background:linear-gradient(135deg,#2f355d,#232845);padding:32px 36px;border-bottom:4px solid #46507d">
    <div style="font-size:10px;color:#ffffff;letter-spacing:2.5px;text-transform:uppercase;font-family:Montserrat,sans-serif;font-weight:700;margin-bottom:8px">Jones Assurance Property Management | Upstate South Carolina</div>
    <h1 style="font-size:28px;font-weight:700;color:#ffffff;margin-bottom:6px;font-family:Montserrat,sans-serif">Rental Market <em style="color:#d7e4f2;font-style:normal">Intelligence</em></h1>
    <div style="font-size:12px;color:#d1d6d1;font-family:Montserrat,sans-serif">{as_of_display} | 10 Markets | Monthly market view</div>
  </div>
  <div style="background:#ffffff;padding:20px 36px;border-bottom:1px solid #d9ded7;display:flex;gap:24px;flex-wrap:wrap">
    <div><div style="font-size:10px;color:#6b716c;text-transform:uppercase;letter-spacing:1px;font-family:Montserrat,sans-serif">Avg MoM Rent</div><div style="font-size:22px;font-weight:800;color:{pct_color(avg_mom)};font-family:Montserrat,sans-serif">{fmt_pct(avg_mom)}</div></div>
    <div><div style="font-size:10px;color:#6b716c;text-transform:uppercase;letter-spacing:1px;font-family:Montserrat,sans-serif">Hottest Market</div><div style="font-size:22px;font-weight:800;color:#fd5315;font-family:Montserrat,sans-serif">{hottest}</div></div>
    <div><div style="font-size:10px;color:#6b716c;text-transform:uppercase;letter-spacing:1px;font-family:Montserrat,sans-serif">Softest Market</div><div style="font-size:22px;font-weight:800;color:#5d729a;font-family:Montserrat,sans-serif">{softest}</div></div>
  </div>
  <div style="padding:28px 36px">
    <div style="background:#ffffff;border:1px solid #d9ded7;border-left:4px solid #2f355d;border-radius:10px;padding:14px 18px;margin-bottom:28px;font-size:13px;font-family:Roboto,sans-serif">
      <strong style="color:#2f355d">View interactive dashboard:</strong>
      <a href="{PAGES_URL}" style="color:#2f355d">{PAGES_URL}</a>
    </div>
    <h2 style="font-size:16px;font-weight:700;color:#2f355d;letter-spacing:1px;margin-bottom:18px;border-bottom:1px solid #d9ded7;padding-bottom:8px;font-family:Montserrat,sans-serif">TIERED MARKET VIEW</h2>
    {build_group_section("headline", trends, insights)}
    {build_group_section("greenville", trends, insights)}
    {build_group_section("spartanburg", trends, insights)}
    {build_group_section("other", trends, insights)}
    <div style="margin-top:40px;padding-top:20px;border-top:1px solid #d9ded7;font-size:11px;color:#6b716c;font-family:Montserrat,sans-serif;text-align:center">
      Jones Assurance Property Management | Rental Market Intelligence | Data: RentCast API<br>
      Auto-generated {datetime.utcnow().strftime('%Y-%m-%d')} | Not financial advice
    </div>
  </div>
</div>
</body>
</html>"""


def main():
    print(f"\n{'=' * 55}")
    print("Email Report Sender")
    print(f"{'=' * 55}")

    trends = json.loads(TRENDS_FILE.read_text()) if TRENDS_FILE.exists() else {}
    insights = json.loads(INSIGHTS_FILE.read_text()) if INSIGHTS_FILE.exists() else {}
    as_of = trends.get("as_of", "")
    as_of_display = datetime.strptime(as_of, "%Y-%m").strftime("%B %Y") if as_of else "-"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Upstate SC Rental Market Intelligence | {as_of_display}"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = RECIPIENT
    msg.attach(MIMEText(build_email_html(trends, insights), "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_ADDRESS, GMAIL_APP_PW)
        smtp.sendmail(GMAIL_ADDRESS, [RECIPIENT], msg.as_string())

    print(f"OK Email sent to {RECIPIENT}\n")


if __name__ == "__main__":
    main()
