# Upstate SC Rental Market Intelligence

Automated monthly rental market dashboard for 10 Upstate South Carolina markets.
Pulls live data from RentCast API, calculates MoM/QoQ/YoY trends, generates
AI-powered analysis via Claude, and emails a full report on the 1st of each month.
Hosted free on GitHub Pages.

## Markets Covered

**Primary (full data)**
- Greenville (29601, 29607, 29609, 29615)
- Spartanburg (29301, 29303, 29306)
- Anderson (29621, 29624)
- Simpsonville (29680, 29681)
- Greer (29650, 29651)

**Foothills & Lakes**
- Easley (29640, 29642)
- Piedmont (29673)
- Liberty (29657)
- Clemson (29631)
- Seneca (29678, 29672)

## One-Time Setup (~30 minutes)

### Step 1 — Create GitHub account and fork this repo
1. Sign up at [github.com](https://github.com) if you don't have an account
2. Click **Fork** (top right of this page) to copy it to your account
3. Your repo URL will be: `https://github.com/YOUR-USERNAME/upstate-sc-rental`

### Step 2 — Enable GitHub Pages
1. In your forked repo, go to **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: **main**, Folder: **/docs**
4. Click Save
5. Your dashboard URL: `https://YOUR-USERNAME.github.io/upstate-sc-rental`

### Step 3 — Get your API keys

**RentCast API (free — 50 calls/month)**
1. Sign up at [app.rentcast.io/app/api](https://app.rentcast.io/app/api)
2. Copy your API key from the dashboard

**Anthropic API**
1. Sign up at [console.anthropic.com](https://console.anthropic.com)
2. Go to API Keys → Create Key
3. Cost per monthly run: ~$0.10–0.15 (Claude Sonnet, 11 market analyses)

**Gmail App Password**
1. Enable 2-Step Verification on your Google account
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Create an app password for "Mail"
4. Save the 16-character password shown

### Step 4 — Add GitHub Secrets
In your repo: **Settings → Secrets and variables → Actions → New repository secret**

Add these 5 secrets:

| Secret Name | Value |
|---|---|
| `RENTCAST_API_KEY` | Your RentCast API key |
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `GMAIL_ADDRESS` | your.email@gmail.com |
| `GMAIL_APP_PASSWORD` | The 16-char app password |
| `REPORT_RECIPIENT` | Email address to receive reports |
| `GITHUB_PAGES_URL` | https://YOUR-USERNAME.github.io/upstate-sc-rental |

### Step 5 — Seed historical data (run once)
In your repo, go to **Actions → Monthly Rental Market Refresh → Run workflow**
and check the "seed" option, OR clone the repo and run locally:

```bash
git clone https://github.com/YOUR-USERNAME/upstate-sc-rental
cd upstate-sc-rental
pip install requests anthropic
python scripts/seed_history.py
git add data/
git commit -m "Seed historical data"
git push
```

### Step 6 — Run your first full refresh
Go to **Actions → Monthly Rental Market Refresh → Run workflow → Run workflow**

This will:
1. Fetch live data from RentCast (18 zip codes)
2. Calculate all trends
3. Generate AI analysis
4. Build and publish the dashboard
5. Send your first email report

## Automatic Monthly Schedule

The workflow runs automatically on the **1st of every month at 7:00 AM ET**.
You can also trigger it manually from the Actions tab anytime.

## Costs

| Item | Monthly Cost |
|---|---|
| GitHub Actions | Free (well within 2,000 min/month limit) |
| GitHub Pages | Free |
| RentCast API | Free (18 calls / 50 included) |
| Anthropic API | ~$0.10–0.15/month |
| Gmail SMTP | Free |
| **Total** | **~$0.15/month** |

## Customization

### Add or remove markets
Edit `scripts/config.py` — add zip codes to `MARKETS` dict.
Each zip = 1 API call against your monthly quota.

### Change the schedule
Edit `.github/workflows/monthly-refresh.yml` — modify the `cron` line.
Format: `'minute hour day-of-month month day-of-week'`
Example for 1st of month at 8 AM ET: `'0 13 1 * *'`

### Change insight depth or focus
Edit the prompts in `scripts/generate_insights.py`.
The `market_prompt()` and `regional_prompt()` functions control what Claude analyzes.

### Change email recipient
Update the `REPORT_RECIPIENT` GitHub Secret.

## File Structure

```
upstate-sc-rental/
├── .github/workflows/
│   └── monthly-refresh.yml    # GitHub Actions schedule
├── scripts/
│   ├── config.py              # Market definitions & zip codes
│   ├── fetch_data.py          # RentCast API calls
│   ├── calculate_trends.py    # MoM/QoQ/YoY calculations
│   ├── generate_insights.py   # Claude AI analysis
│   ├── build_dashboard.py     # HTML dashboard generator
│   ├── send_email.py          # Gmail email report
│   └── seed_history.py        # One-time historical data bootstrap
├── data/
│   ├── history.json           # Grows by ~18 records each month
│   ├── trends.json            # Latest trend calculations
│   ├── insights.json          # Latest AI analysis
│   └── raw_latest.json        # Raw RentCast API response (for debugging)
├── docs/
│   └── index.html             # Live dashboard (served by GitHub Pages)
└── README.md
```

## Troubleshooting

**"RentCast returned no data for a zip"**
Small markets (Liberty, Seneca) may have sparse data. The script handles this gracefully — it averages available zips and skips nulls.

**"Gmail send failed"**
Make sure you're using an App Password (not your regular Gmail password) and that 2-Step Verification is enabled on your Google account.

**"Actions workflow not running"**
GitHub sometimes pauses scheduled workflows on repos with no recent activity. Go to Actions and manually trigger the workflow once to re-enable the schedule.

**"Dashboard shows — for all values"**
Run `seed_history.py` first to bootstrap historical data, then run a full workflow refresh.
