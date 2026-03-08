#!/usr/bin/env python3
"""
send_email.py
Sends a rich HTML email report via Gmail SMTP.
Requires a Gmail App Password (not your regular Gmail password).
Setup: Google Account → Security → 2-Step Verification → App Passwords → generate one.
Store it in GitHub Secrets as GMAIL_APP_PASSWORD.
"""

import os
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from datetime import datetime

TRENDS_FILE   = Path(__file__).parent.parent / "data" / "trends.json"
INSIGHTS_FILE = Path(__file__).parent.parent / "data" / "insights.json"

import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import MARKETS

GMAIL_ADDRESS    = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PW     = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENT        = os.environ["REPORT_RECIPIENT"]
PAGES_URL        = os.environ.get("GITHUB_PAGES_URL", "https://your-username.github.io/upstate-sc-rental")

def fmt_rent(v):
    if v is None: return "—"
    return f"${v:,.0f}"

def fmt_pct(v):
    if v is None: return "—"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.1f}%"

def pct_color(v):
    if v is None: return "#666"
    return "#4caf50" if v > 0 else "#ef5350" if v < 0 else "#888"

def temp_color(temp):
    return {
        "hot": "#e07a6a", "warm": "#f4a235",
        "neutral": "#86b96e", "cool": "#7eb3d4", "cold": "#b99ddb"
    }.get(temp, "#86b96e")

def build_market_row(mkt_key, trends, insights):
    mkt_cfg = MARKETS[mkt_key]
    mt      = trends["markets"].get(mkt_key, {})
    agg     = mt.get("aggregate", {})
    cond    = mt.get("market_conditions", {})
    color   = mkt_cfg["color"]
    tc      = temp_color(cond.get("temperature"))

    rent_cur = agg.get("averageRent", {}).get("current")
    rent_mom = agg.get("averageRent", {}).get("changes", {}).get("mom", {}).get("pct_change")
    rent_qoq = agg.get("averageRent", {}).get("changes", {}).get("qoq", {}).get("pct_change")
    rent_yoy = agg.get("averageRent", {}).get("changes", {}).get("yoy", {}).get("pct_change")
    dom_cur  = agg.get("averageDaysOnMarket", {}).get("current")
    inv_cur  = agg.get("totalListings", {}).get("current")

    insight_text = insights.get("markets", {}).get(mkt_key, "")
    # Extract just the renewal strategy paragraph for the email teaser
    renewal_start = insight_text.find("RENEWAL PRICING STRATEGY")
    if renewal_start != -1:
        renewal_snippet = insight_text[renewal_start + len("RENEWAL PRICING STRATEGY"):].strip()
        renewal_snippet = renewal_snippet[:350].rsplit(" ", 1)[0] + "…"
    else:
        renewal_snippet = insight_text[:350].rsplit(" ", 1)[0] + "…" if insight_text else "See full report."

    return f"""
    <tr>
      <td style="padding:12px 14px;border-bottom:1px solid #1a2f20;font-weight:bold;color:{color};white-space:nowrap">{mkt_cfg['name']}</td>
      <td style="padding:12px 14px;border-bottom:1px solid #1a2f20;font-size:16px;font-weight:800;color:#f0f5e8;white-space:nowrap">{fmt_rent(rent_cur)}</td>
      <td style="padding:12px 14px;border-bottom:1px solid #1a2f20;color:{pct_color(rent_mom)};font-weight:700;white-space:nowrap">{fmt_pct(rent_mom)}</td>
      <td style="padding:12px 14px;border-bottom:1px solid #1a2f20;color:{pct_color(rent_qoq)};font-weight:700;white-space:nowrap">{fmt_pct(rent_qoq)}</td>
      <td style="padding:12px 14px;border-bottom:1px solid #1a2f20;color:{pct_color(rent_yoy)};font-weight:700;white-space:nowrap">{fmt_pct(rent_yoy)}</td>
      <td style="padding:12px 14px;border-bottom:1px solid #1a2f20;white-space:nowrap">{f'{dom_cur:.0f}d' if dom_cur else '—'}</td>
      <td style="padding:12px 14px;border-bottom:1px solid #1a2f20;white-space:nowrap">{f'{inv_cur:,.0f}' if inv_cur else '—'}</td>
      <td style="padding:12px 14px;border-bottom:1px solid #1a2f20"><span style="background:{tc}22;color:{tc};border:1px solid {tc}55;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;white-space:nowrap">{cond.get('temperature_label','—')}</span></td>
    </tr>
    <tr>
      <td colspan="8" style="padding:6px 14px 16px 14px;border-bottom:1px solid #0d1f14;font-size:12px;color:#7a9a70;font-style:italic;line-height:1.5">
        <strong style="color:#86b96e;font-style:normal">Renewal rec:</strong> {renewal_snippet}
      </td>
    </tr>"""

def build_market_insight_section(mkt_key, insights):
    mkt_cfg = MARKETS[mkt_key]
    color   = mkt_cfg["color"]
    text    = insights.get("markets", {}).get(mkt_key, "No analysis available.")

    headers = [
        "MARKET CONDITIONS", "IMPLICATIONS FOR CURRENT OWNERS",
        "VACANCY MARKETING STRATEGY", "RENEWAL PRICING STRATEGY"
    ]
    html = text
    for h in headers:
        html = html.replace(h,
            f'<div style="font-size:10px;color:{color};letter-spacing:1.5px;text-transform:uppercase;'
            f'font-family:Courier New,monospace;margin:18px 0 6px;font-weight:bold">{h}</div>'
        )
    paragraphs = []
    for chunk in html.split("\n\n"):
        chunk = chunk.strip()
        if not chunk: continue
        if chunk.startswith("<div"):
            paragraphs.append(chunk)
        else:
            paragraphs.append(f'<p style="font-size:13px;color:#b8c8b0;line-height:1.75;margin:0 0 12px">{chunk}</p>')

    return f"""
    <div style="margin-bottom:32px;border-left:3px solid {color};padding-left:18px">
      <h3 style="color:{color};font-size:17px;font-weight:400;margin-bottom:14px">{mkt_cfg['name']}</h3>
      {''.join(paragraphs)}
    </div>"""

def build_email_html(trends, insights):
    as_of = trends.get("as_of", "")
    as_of_display = datetime.strptime(as_of, "%Y-%m").strftime("%B %Y") if as_of else "—"
    rs = trends.get("regional_summary", {})
    hottest = MARKETS.get(rs.get("hottest_market", ""), {}).get("name", "—")
    softest = MARKETS.get(rs.get("softest_market", ""), {}).get("name", "—")
    avg_yoy = rs.get("avg_rent_yoy_pct")
    yoy_color = "#4caf50" if (avg_yoy or 0) >= 0 else "#ef5350"

    # Market rows for summary table
    primary_rows = "".join(build_market_row(k, trends, insights) for k, v in MARKETS.items() if v["tier"] == "primary")
    foothills_rows = "".join(build_market_row(k, trends, insights) for k, v in MARKETS.items() if v["tier"] == "foothills")

    # Full insight sections
    primary_insights = "".join(build_market_insight_section(k, insights) for k, v in MARKETS.items() if v["tier"] == "primary")
    foothills_insights = "".join(build_market_insight_section(k, insights) for k, v in MARKETS.items() if v["tier"] == "foothills")

    # Regional insight
    regional_text = insights.get("regional", "")
    regional_html = ""
    for chunk in regional_text.split("\n\n"):
        chunk = chunk.strip()
        if not chunk: continue
        for h in ["UPSTATE SC MACRO VIEW", "CROSS-MARKET INVESTMENT THESIS", "OUTLOOK AND RISKS"]:
            chunk = chunk.replace(h, f'<div style="font-size:10px;color:#86b96e;letter-spacing:1.5px;text-transform:uppercase;font-family:Courier New,monospace;margin:18px 0 6px;font-weight:bold">{h}</div>')
        if not chunk.startswith("<div"):
            chunk = f'<p style="font-size:13px;color:#b8c8b0;line-height:1.75;margin:0 0 12px">{chunk}</p>'
        regional_html += chunk

    table_header = """
    <tr style="background:#0a1f10">
      <th style="padding:10px 14px;text-align:left;color:#4a6040;font-size:10px;letter-spacing:.5px;text-transform:uppercase;font-family:Courier New,monospace">Market</th>
      <th style="padding:10px 14px;text-align:left;color:#4a6040;font-size:10px;letter-spacing:.5px;text-transform:uppercase">Avg Rent</th>
      <th style="padding:10px 14px;text-align:left;color:#4a6040;font-size:10px;letter-spacing:.5px;text-transform:uppercase">MoM</th>
      <th style="padding:10px 14px;text-align:left;color:#4a6040;font-size:10px;letter-spacing:.5px;text-transform:uppercase">QoQ</th>
      <th style="padding:10px 14px;text-align:left;color:#4a6040;font-size:10px;letter-spacing:.5px;text-transform:uppercase">YoY</th>
      <th style="padding:10px 14px;text-align:left;color:#4a6040;font-size:10px;letter-spacing:.5px;text-transform:uppercase">DOM</th>
      <th style="padding:10px 14px;text-align:left;color:#4a6040;font-size:10px;letter-spacing:.5px;text-transform:uppercase">Listings</th>
      <th style="padding:10px 14px;text-align:left;color:#4a6040;font-size:10px;letter-spacing:.5px;text-transform:uppercase">Temp</th>
    </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/></head>
<body style="background:#0d1a14;color:#e8efe0;font-family:Georgia,serif;margin:0;padding:0">

<div style="max-width:900px;margin:0 auto;padding:0 0 40px">

  <!-- Header -->
  <div style="background:linear-gradient(170deg,#0a1f10,#0d1a14);padding:32px 36px;border-bottom:1px solid rgba(134,185,110,.2)">
    <div style="font-size:10px;color:#86b96e;letter-spacing:2.5px;text-transform:uppercase;font-family:Courier New,monospace;margin-bottom:8px">🏠 Upstate SC Rental Market · Monthly Report</div>
    <h1 style="font-size:26px;font-weight:400;color:#f0f5e8;margin-bottom:6px">Rental Market <em style="color:#86b96e">Intelligence</em></h1>
    <div style="font-size:12px;color:#4a6040;font-family:Courier New,monospace">{as_of_display} · 10 Markets · RentCast + Claude AI</div>
  </div>

  <!-- Hero stats -->
  <div style="background:#0a1a10;padding:20px 36px;border-bottom:1px solid rgba(255,255,255,.04);display:flex;gap:24px;flex-wrap:wrap">
    <div><div style="font-size:10px;color:#4a6040;text-transform:uppercase;letter-spacing:1px;font-family:Courier New,monospace">Avg YoY Rent</div><div style="font-size:22px;font-weight:800;color:{yoy_color};font-family:sans-serif">{fmt_pct(avg_yoy)}</div></div>
    <div><div style="font-size:10px;color:#4a6040;text-transform:uppercase;letter-spacing:1px;font-family:Courier New,monospace">Hottest Market</div><div style="font-size:22px;font-weight:800;color:#f4a235;font-family:sans-serif">{hottest}</div></div>
    <div><div style="font-size:10px;color:#4a6040;text-transform:uppercase;letter-spacing:1px;font-family:Courier New,monospace">Softest Market</div><div style="font-size:22px;font-weight:800;color:#7eb3d4;font-family:sans-serif">{softest}</div></div>
    <div><div style="font-size:10px;color:#4a6040;text-transform:uppercase;letter-spacing:1px;font-family:Courier New,monospace">Markets Growing</div><div style="font-size:22px;font-weight:800;color:#86b96e;font-family:sans-serif">{rs.get('markets_with_rent_growth','—')}/10</div></div>
  </div>

  <div style="padding:28px 36px">

    <!-- Dashboard link -->
    <div style="background:rgba(134,185,110,.08);border:1px solid rgba(134,185,110,.2);border-radius:10px;padding:14px 18px;margin-bottom:28px;font-size:13px;font-family:sans-serif">
      📊 <strong style="color:#86b96e">View interactive dashboard:</strong>
      <a href="{PAGES_URL}" style="color:#7eb3d4">{PAGES_URL}</a>
    </div>

    <!-- Regional analysis -->
    <h2 style="font-size:16px;font-weight:400;color:#86b96e;letter-spacing:1px;margin-bottom:18px;border-bottom:1px solid rgba(134,185,110,.2);padding-bottom:8px">REGIONAL EXECUTIVE SUMMARY</h2>
    <div style="margin-bottom:36px">{regional_html}</div>

    <!-- Primary markets table -->
    <h2 style="font-size:16px;font-weight:400;color:#86b96e;letter-spacing:1px;margin-bottom:14px;border-bottom:1px solid rgba(134,185,110,.2);padding-bottom:8px">PRIMARY MARKETS SNAPSHOT</h2>
    <div style="overflow-x:auto;margin-bottom:36px">
      <table style="width:100%;border-collapse:collapse;background:#0a1a10;border-radius:10px;overflow:hidden">
        <thead>{table_header}</thead>
        <tbody>{primary_rows}</tbody>
      </table>
    </div>

    <!-- Foothills markets table -->
    <h2 style="font-size:16px;font-weight:400;color:#c4a36e;letter-spacing:1px;margin-bottom:14px;border-bottom:1px solid rgba(196,163,110,.2);padding-bottom:8px">FOOTHILLS &amp; LAKES MARKETS</h2>
    <div style="overflow-x:auto;margin-bottom:36px">
      <table style="width:100%;border-collapse:collapse;background:#0a1a10;border-radius:10px;overflow:hidden">
        <thead>{table_header}</thead>
        <tbody>{foothills_rows}</tbody>
      </table>
    </div>

    <!-- Full per-market analysis -->
    <h2 style="font-size:16px;font-weight:400;color:#86b96e;letter-spacing:1px;margin-bottom:24px;border-bottom:1px solid rgba(134,185,110,.2);padding-bottom:8px">FULL MARKET ANALYSIS — PRIMARY MARKETS</h2>
    {primary_insights}

    <h2 style="font-size:16px;font-weight:400;color:#c4a36e;letter-spacing:1px;margin-bottom:24px;border-bottom:1px solid rgba(196,163,110,.2);padding-bottom:8px">FULL MARKET ANALYSIS — FOOTHILLS &amp; LAKES</h2>
    {foothills_insights}

    <!-- Footer -->
    <div style="margin-top:40px;padding-top:20px;border-top:1px solid rgba(255,255,255,.06);font-size:11px;color:#2a4030;font-family:Courier New,monospace;text-align:center">
      Upstate SC Rental Market Intelligence · Data: RentCast API · Analysis: Claude AI<br>
      Auto-generated {datetime.utcnow().strftime('%Y-%m-%d')} · Not financial advice
    </div>
  </div>
</div>
</body>
</html>"""

def main():
    print(f"\n{'='*55}")
    print("Email Report Sender")
    print(f"{'='*55}")

    trends   = json.loads(TRENDS_FILE.read_text())  if TRENDS_FILE.exists()  else {}
    insights = json.loads(INSIGHTS_FILE.read_text()) if INSIGHTS_FILE.exists() else {}

    as_of = trends.get("as_of", "")
    as_of_display = datetime.strptime(as_of, "%Y-%m").strftime("%B %Y") if as_of else "—"

    html_body = build_email_html(trends, insights)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Upstate SC Rental Market Report — {as_of_display}"
    msg["From"]    = f"Rental Market Bot <{GMAIL_ADDRESS}>"
    msg["To"]      = RECIPIENT

    # Plain text fallback
    rs = trends.get("regional_summary", {})
    plain = (
        f"Upstate SC Rental Market Report — {as_of_display}\n\n"
        f"Avg YoY Rent Change: {fmt_pct(rs.get('avg_rent_yoy_pct'))}\n"
        f"Hottest Market: {MARKETS.get(rs.get('hottest_market',''),{}).get('name','—')}\n"
        f"Softest Market: {MARKETS.get(rs.get('softest_market',''),{}).get('name','—')}\n\n"
        f"View full dashboard: {PAGES_URL}\n\n"
        "Auto-generated by Upstate SC Rental Market Intelligence."
    )
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    print(f"Sending to {RECIPIENT}...")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_ADDRESS, GMAIL_APP_PW)
            smtp.sendmail(GMAIL_ADDRESS, RECIPIENT, msg.as_string())
        print(f"✅ Email sent — {as_of_display} report delivered\n")
    except Exception as e:
        print(f"✗ Email failed: {e}")
        raise

if __name__ == "__main__":
    main()
