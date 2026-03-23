import os
import json
import asyncio
import hashlib
import smtplib
import gspread
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

# ── Config ────────────────────────────────────────────────────────────────────

SEARCH_TERMS = [
    "中古 ハウスパイプ",
    "中古 農業用パイプ",
    "中古 単管パイプ",
    "ビニールハウス パイプ 中古",
    "ハウス 骨材 中古",
    "ハウス部材 中古",
    "温室 パイプ 中古",
]

GMAIL_USER    = os.environ["GMAIL_USER"]
GMAIL_PASS    = os.environ["GMAIL_APP_PASSWORD"]   # Gmail App Password
NOTIFY_EMAIL  = os.environ["NOTIFY_EMAIL"]         # usually same as GMAIL_USER
SHEET_ID      = os.environ["GOOGLE_SHEET_ID"]
GCP_CREDS_JSON = os.environ["GCP_SERVICE_ACCOUNT_JSON"]  # full JSON string

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ── Google Sheets ─────────────────────────────────────────────────────────────

def get_sheet():
    creds_dict = json.loads(GCP_CREDS_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    sh = client.open_by_key(SHEET_ID)

    # "Listings" tab
    try:
        ws = sh.worksheet("Listings")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="Listings", rows=5000, cols=10)
        ws.append_row(["ID", "Site", "Title", "Price", "URL", "Search Term", "Found At"])

    # "Seen" tab — stores hashes of already-notified listings
    try:
        seen_ws = sh.worksheet("Seen")
    except gspread.WorksheetNotFound:
        seen_ws = sh.add_worksheet(title="Seen", rows=50000, cols=2)
        seen_ws.append_row(["Hash", "Date"])

    return ws, seen_ws


def load_seen_hashes(seen_ws):
    rows = seen_ws.get_all_values()
    return set(row[0] for row in rows[1:] if row)  # skip header


def save_new_listings(ws, seen_ws, listings, seen_hashes):
    new_listings = []
    new_hashes   = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    for l in listings:
        h = hashlib.md5(l["url"].encode()).hexdigest()
        if h not in seen_hashes:
            new_listings.append(l)
            new_hashes.append([h, now])
            ws.append_row([
                h,
                l["site"],
                l["title"],
                l["price"],
                l["url"],
                l["term"],
                now,
            ])

    if new_hashes:
        seen_ws.append_rows(new_hashes)

    return new_listings


# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(new_listings):
    if not new_listings:
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🌿 {len(new_listings)} new greenhouse pipe listing(s) found"
    msg["From"]    = GMAIL_USER
    msg["To"]      = NOTIFY_EMAIL

    # Plain text
    text_lines = [f"Found {len(new_listings)} new listing(s):\n"]
    for l in new_listings:
        text_lines.append(f"[{l['site']}] {l['title']}")
        text_lines.append(f"  Price: {l['price']}")
        text_lines.append(f"  URL:   {l['url']}\n")
    text = "\n".join(text_lines)

    # HTML
    rows = ""
    for l in new_listings:
        rows += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #eee;font-weight:600;color:#2d6a2d">{l['site']}</td>
          <td style="padding:8px;border-bottom:1px solid #eee"><a href="{l['url']}" style="color:#1a5c1a;text-decoration:none">{l['title']}</a></td>
          <td style="padding:8px;border-bottom:1px solid #eee;white-space:nowrap">{l['price']}</td>
        </tr>"""

    html = f"""
    <div style="font-family:sans-serif;max-width:700px;margin:0 auto">
      <div style="background:#2d6a2d;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="color:#fff;margin:0">🌿 Greenhouse Pipe Alert</h2>
        <p style="color:#a8d5a8;margin:4px 0 0">{len(new_listings)} new listing(s) found</p>
      </div>
      <table style="width:100%;border-collapse:collapse;background:#fff">
        <thead>
          <tr style="background:#f4f9f4">
            <th style="padding:10px 8px;text-align:left;color:#555">Site</th>
            <th style="padding:10px 8px;text-align:left;color:#555">Title</th>
            <th style="padding:10px 8px;text-align:left;color:#555">Price</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
      <p style="color:#888;font-size:12px;padding:12px">
        Full list in your <a href="https://docs.google.com/spreadsheets/d/{SHEET_ID}">Google Sheet</a>
      </p>
    </div>"""

    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_PASS)
        server.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())

    print(f"✉️  Email sent — {len(new_listings)} new listing(s)")


# ── Scrapers ──────────────────────────────────────────────────────────────────

async def scrape_yahoo(page, term):
    listings = []
    url = f"https://auctions.yahoo.co.jp/search/search?p={term}&auccat=0&tab_ex=commerce&ei=utf-8"
    try:
        await page.goto(url, timeout=30000)
        await page.wait_for_selector("li.Product", timeout=15000)
        items = await page.query_selector_all("li.Product")
        for item in items[:20]:
            try:
                title_el = await item.query_selector(".Product__title")
                price_el = await item.query_selector(".Product__priceValue")
                link_el  = await item.query_selector("a.Product__imageLink, a.Product__titleLink")
                title = await title_el.inner_text() if title_el else "—"
                price = await price_el.inner_text() if price_el else "—"
                href  = await link_el.get_attribute("href") if link_el else ""
                if href:
                    listings.append({"site": "Yahoo", "title": title.strip(), "price": price.strip(), "url": href, "term": term})
            except Exception:
                continue
    except Exception as e:
        print(f"Yahoo error [{term}]: {e}")
    return listings


async def scrape_mercari(page, term):
    listings = []
    url = f"https://jp.mercari.com/search?keyword={term}&status=on_sale"
    try:
        await page.goto(url, timeout=30000)
        await page.wait_for_selector("[data-testid='item-cell']", timeout=15000)
        items = await page.query_selector_all("[data-testid='item-cell']")
        for item in items[:20]:
            try:
                title_el = await item.query_selector("[data-testid='item-name']")
                price_el = await item.query_selector("[data-testid='item-price']")
                link_el  = await item.query_selector("a")
                title = await title_el.inner_text() if title_el else "—"
                price = await price_el.inner_text() if price_el else "—"
                href  = await link_el.get_attribute("href") if link_el else ""
                if href:
                    full_url = f"https://jp.mercari.com{href}" if href.startswith("/") else href
                    listings.append({"site": "Mercari", "title": title.strip(), "price": price.strip(), "url": full_url, "term": term})
            except Exception:
                continue
    except Exception as e:
        print(f"Mercari error [{term}]: {e}")
    return listings


async def scrape_jmty(page, term):
    listings = []
    url = f"https://jmty.jp/all/sale?keyword={term}"
    try:
        await page.goto(url, timeout=30000)
        await page.wait_for_selector("li.p-list-item", timeout=15000)
        items = await page.query_selector_all("li.p-list-item")
        for item in items[:20]:
            try:
                title_el = await item.query_selector(".p-item-title")
                price_el = await item.query_selector(".p-item-most-important")
                link_el  = await item.query_selector("a")
                title = await title_el.inner_text() if title_el else "—"
                price = await price_el.inner_text() if price_el else "—"
                href  = await link_el.get_attribute("href") if link_el else ""
                if href:
                    full_url = f"https://jmty.jp{href}" if href.startswith("/") else href
                    listings.append({"site": "JMTY", "title": title.strip(), "price": price.strip(), "url": full_url, "term": term})
            except Exception:
                continue
    except Exception as e:
        print(f"JMTY error [{term}]: {e}")
    return listings


# ── Main ──────────────────────────────────────────────────────────────────────

async def run():
    all_listings = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ja-JP",
        )
        page = await context.new_page()

        for term in SEARCH_TERMS:
            print(f"🔍 Searching: {term}")
            yahoo   = await scrape_yahoo(page, term)
            mercari = await scrape_mercari(page, term)
            jmty    = await scrape_jmty(page, term)
            all_listings.extend(yahoo + mercari + jmty)
            print(f"   Yahoo: {len(yahoo)}, Mercari: {len(mercari)}, JMTY: {len(jmty)}")
            await asyncio.sleep(2)  # polite delay

        await browser.close()

    print(f"\n📦 Total listings found: {len(all_listings)}")

    ws, seen_ws   = get_sheet()
    seen_hashes   = load_seen_hashes(seen_ws)
    new_listings  = save_new_listings(ws, seen_ws, all_listings, seen_hashes)

    print(f"🆕 New listings: {len(new_listings)}")

    if new_listings:
        send_email(new_listings)
    else:
        print("No new listings — no email sent")


if __name__ == "__main__":
    asyncio.run(run())
