import os
import json
import time
import hashlib
import smtplib
import requests
import gspread
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.oauth2.service_account import Credentials
from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────────────

SEARCH_TERMS = [
    "中古 ハウスパイプ",
    "中古 農業用パイプ",
    "中古 単管パイプ",
    "ビニールハウス パイプ 中古",
    "ハウス 骨材 中古",
    "ハウス部材 中古",
    "温室 パイプ 中古",
    "ビニールハウス 直管",
    "直管パイプ 中古",
    "直管 農業用 中古",
    "ハウス 直管 中古",
    "中古 直管",
]

GMAIL_USER        = os.environ["GMAIL_USER"]
GMAIL_PASS        = os.environ["GMAIL_APP_PASSWORD"]
NOTIFY_EMAIL      = os.environ["NOTIFY_EMAIL"]
SHEET_ID          = os.environ["GOOGLE_SHEET_ID"]
GCP_CREDS_JSON    = os.environ["GCP_SERVICE_ACCOUNT_JSON"]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja-JP,ja;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUIRED_KEYWORDS = ["パイプ", "pipe", "骨材", "部材", "単管"]

def is_relevant(title):
    title_lower = title.lower()
    return any(kw.lower() in title_lower for kw in REQUIRED_KEYWORDS)

# ── Google Sheets ─────────────────────────────────────────────────────────────

def get_sheet():
    creds_dict = json.loads(GCP_CREDS_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    sh = client.open_by_key(SHEET_ID)

    try:
        ws = sh.worksheet("Listings")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="Listings", rows=5000, cols=10)
        ws.append_row(["ID", "Site", "Title", "Price", "URL", "Image", "Search Term", "Found At"])

    try:
        seen_ws = sh.worksheet("Seen")
    except gspread.WorksheetNotFound:
        seen_ws = sh.add_worksheet(title="Seen", rows=50000, cols=2)
        seen_ws.append_row(["Hash", "Date"])

    return ws, seen_ws


def load_seen_hashes(seen_ws):
    rows = seen_ws.get_all_values()
    return set(row[0] for row in rows[1:] if row)


def save_new_listings(ws, seen_ws, listings, seen_hashes):
    new_listings = []
    new_hashes   = []
    new_rows     = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    for l in listings:
        h = hashlib.md5(l["url"].encode()).hexdigest()
        if h not in seen_hashes:
            new_listings.append(l)
            new_hashes.append([h, now])
            img_formula = f'=IMAGE("{l["image"]}")' if l.get("image") else ""
            new_rows.append([h, l["site"], l["title"], l["price"], l["url"], img_formula, l["term"], now])

    if new_rows:
        ws.append_rows(new_rows)
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

    text_lines = [f"Found {len(new_listings)} new listing(s):\n"]
    for l in new_listings:
        text_lines.append(f"[{l['site']}] {l['title']}")
        text_lines.append(f"  Price: {l['price']}")
        text_lines.append(f"  URL:   {l['url']}\n")

    rows = ""
    for l in new_listings:
        rows += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #eee;font-weight:600;color:#2d6a2d">{l['site']}</td>
          <td style="padding:8px;border-bottom:1px solid #eee"><a href="{l['url']}" style="color:#1a5c1a">{l['title']}</a></td>
          <td style="padding:8px;border-bottom:1px solid #eee;white-space:nowrap">{l['price']}</td>
        </tr>"""

    html = f"""
    <div style="font-family:sans-serif;max-width:700px;margin:0 auto">
      <div style="background:#2d6a2d;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="color:#fff;margin:0">🌿 Greenhouse Pipe Alert</h2>
        <p style="color:#a8d5a8;margin:4px 0 0">{len(new_listings)} new listing(s)</p>
      </div>
      <table style="width:100%;border-collapse:collapse;background:#fff">
        <thead><tr style="background:#f4f9f4">
          <th style="padding:10px 8px;text-align:left;color:#555">Site</th>
          <th style="padding:10px 8px;text-align:left;color:#555">Title</th>
          <th style="padding:10px 8px;text-align:left;color:#555">Price</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
      <p style="color:#888;font-size:12px;padding:12px">
        Full list in your <a href="https://docs.google.com/spreadsheets/d/{SHEET_ID}">Google Sheet</a>
      </p>
    </div>"""

    msg.attach(MIMEText("\n".join(text_lines), "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_PASS)
        server.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())

    print(f"✉️  Email sent — {len(new_listings)} new listing(s)")

# ── Scrapers ──────────────────────────────────────────────────────────────────

def scrape_yahoo(term):
    listings = []
    url = f"https://auctions.yahoo.co.jp/search/search?p={requests.utils.quote(term)}&auccat=0&tab_ex=commerce&ei=utf-8"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select("li.Product")
        for item in items[:20]:
            title_el = item.select_one(".Product__title")
            price_el = item.select_one(".Product__priceValue")
            link_el  = item.select_one("a.Product__imageLink, a.Product__titleLink")
            img_el   = item.select_one("img")
            title = title_el.get_text(strip=True) if title_el else "—"
            price = price_el.get_text(strip=True) if price_el else "—"
            href  = link_el["href"] if link_el else ""
            image = img_el.get("src") or img_el.get("data-src") or "" if img_el else ""
            if href and is_relevant(title):
                listings.append({"site": "Yahoo", "title": title, "price": price, "url": href, "image": image, "term": term})
    except Exception as e:
        print(f"Yahoo error [{term}]: {e}")
    return listings


def scrape_mercari(term):
    listings = []
    # Mercari has a search API endpoint
    url = f"https://api.mercari.jp/v2/entities:search"
    payload = {
        "pageSize": 20,
        "pageToken": "",
        "searchSessionId": "",
        "indexRouting": "INDEX_ROUTING_UNSPECIFIED",
        "thumbnailTypes": [],
        "searchCondition": {
            "keyword": term,
            "excludeKeyword": "",
            "sort": "SORT_CREATED_TIME",
            "order": "ORDER_DESC",
            "status": ["STATUS_ON_SALE"],
            "sizeId": [],
            "categoryId": [],
            "brandId": [],
            "sellerId": [],
            "priceMin": 0,
            "priceMax": 0,
            "itemConditionId": [],
            "shippingPayerId": [],
            "shippingFromArea": [],
            "shippingMethod": [],
            "colorId": [],
            "hasCoupon": False,
            "attributes": [],
            "itemTypes": [],
            "skuIds": []
        },
        "userId": "",
        "pageSize": 20
    }
    api_headers = {
        **HEADERS,
        "Content-Type": "application/json; charset=utf-8",
        "X-Platform": "web",
        "Accept": "application/json",
        "DPoP": "dummy",
    }
    try:
        r = requests.post(url, json=payload, headers=api_headers, timeout=15)
        data = r.json()
        for item in data.get("items", [])[:20]:
            title = item.get("name", "—")
            price = f"¥{item.get('price', '—'):,}" if isinstance(item.get("price"), int) else "—"
            item_id = item.get("id", "")
            href = f"https://jp.mercari.com/item/{item_id}" if item_id else ""
            image = item.get("thumbnails", [{}])[0].get("url", "") if item.get("thumbnails") else ""
            if href and is_relevant(title):
                listings.append({"site": "Mercari", "title": title, "price": price, "url": href, "image": image, "term": term})
    except Exception as e:
        print(f"Mercari error [{term}]: {e}")
    return listings


def scrape_jmty(term):
    listings = []
    url = f"https://jmty.jp/all/sale?keyword={requests.utils.quote(term)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select("li.p-list-item")
        for item in items[:20]:
            title_el = item.select_one(".p-item-title")
            price_el = item.select_one(".p-item-most-important")
            link_el  = item.select_one("a")
            title = title_el.get_text(strip=True) if title_el else "—"
            price = price_el.get_text(strip=True) if price_el else "—"
            href  = link_el["href"] if link_el else ""
            img_el = item.select_one("img")
            image = img_el.get("src") or img_el.get("data-src") or "" if img_el else ""
            if href and is_relevant(title):
                full_url = f"https://jmty.jp{href}" if href.startswith("/") else href
                listings.append({"site": "JMTY", "title": title, "price": price, "url": full_url, "image": image, "term": term})
    except Exception as e:
        print(f"JMTY error [{term}]: {e}")
    return listings

# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    all_listings = []

    for term in SEARCH_TERMS:
        print(f"🔍 Searching: {term}")
        yahoo   = scrape_yahoo(term)
        mercari = scrape_mercari(term)
        jmty    = scrape_jmty(term)
        all_listings.extend(yahoo + mercari + jmty)
        print(f"   Yahoo: {len(yahoo)}, Mercari: {len(mercari)}, JMTY: {len(jmty)}")
        time.sleep(2)

    # Deduplicate by URL across all search terms
    seen_urls = set()
    deduped = []
    for l in all_listings:
        if l["url"] not in seen_urls:
            seen_urls.add(l["url"])
            deduped.append(l)
    all_listings = deduped

    print(f"\n📦 Total listings found: {len(all_listings)} (after dedup)")

    ws, seen_ws  = get_sheet()
    seen_hashes  = load_seen_hashes(seen_ws)
    new_listings = save_new_listings(ws, seen_ws, all_listings, seen_hashes)

    print(f"🆕 New listings: {len(new_listings)}")

    if new_listings:
        send_email(new_listings)
    else:
        print("No new listings — no email sent")


if __name__ == "__main__":
    run()
