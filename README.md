# 🌿 Greenhouse Pipe Scraper

Scrapes Yahoo Auctions, Mercari, and JMTY for used greenhouse pipe listings.  
Runs twice daily via GitHub Actions. New listings → Google Sheet + Gmail alert.

---

## Setup (one-time)

### 1. Create a GitHub repo

Push this folder to a new private GitHub repo.

---

### 2. Google Sheet

1. Create a new Google Sheet
2. Copy the Sheet ID from the URL:  
   `https://docs.google.com/spreadsheets/d/THIS_PART_HERE/edit`
3. The scraper will auto-create two tabs: **Listings** and **Seen**

---

### 3. Google Service Account (for Sheets access)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or use existing)
3. Enable **Google Sheets API** and **Google Drive API**
4. Go to **IAM & Admin → Service Accounts → Create Service Account**
5. Give it any name, click through to finish
6. Click the service account → **Keys → Add Key → JSON**
7. Download the JSON file — keep it safe
8. **Share your Google Sheet** with the service account email  
   (looks like `name@project.iam.gserviceaccount.com`) — give it **Editor** access

---

### 4. Gmail App Password

1. Go to your Google Account → Security
2. Enable **2-Step Verification** if not already on
3. Search for **App Passwords**
4. Create one — name it "Greenhouse Scraper"
5. Copy the 16-character password

---

### 5. GitHub Secrets

In your GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**

Add these secrets:

| Secret Name | Value |
|---|---|
| `GMAIL_USER` | your Gmail address |
| `GMAIL_APP_PASSWORD` | the 16-char app password from step 4 |
| `NOTIFY_EMAIL` | email to send alerts to (can be same as above) |
| `GOOGLE_SHEET_ID` | the Sheet ID from step 2 |
| `GCP_SERVICE_ACCOUNT_JSON` | the **entire contents** of the JSON file from step 3 |

---

## Schedule

Runs automatically at:
- **10:00 AM JST** daily
- **7:00 AM JST** daily (second run)

To run manually: GitHub repo → **Actions → Greenhouse Pipe Scraper → Run workflow**

---

## Search Terms

Edit `scraper/scraper.py` → `SEARCH_TERMS` list to add/remove terms.

Current terms:
- 中古 ハウスパイプ
- 中古 農業用パイプ
- 中古 単管パイプ
- ビニールハウス パイプ 中古
- ハウス 骨材 中古
- ハウス部材 中古
- 温室 パイプ 中古

---

## How it works

1. GitHub Actions wakes up on schedule
2. Playwright (headless Chromium) searches each term on all 3 sites
3. Results are hashed — only **new** listings (not seen before) are saved
4. New listings are appended to the **Listings** tab in Google Sheets
5. A Gmail alert is sent with a summary of new listings
6. Seen hashes are stored in the **Seen** tab to avoid duplicate alerts
