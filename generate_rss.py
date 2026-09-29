#!/usr/bin/env python3
"""
Multi-website RSS feed generator.
- TOI: uses Chrome (Selenium) for browsing, extracts image, title, rating,
  language, genre, duration, date release — in website order
- 91Mobiles: uses requests
- 1TamilMV: uses requests
- Sequential fetch: one URL at a time, store, generate, clear, next
"""

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
import re
import json
import time

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION — change URLs here for future updates
# ═══════════════════════════════════════════════════════════════

LINKS = {
    "toi": {
        "tamil":     "https://timesofindia.indiatimes.com/entertainment/latest-new-movies/tamil-movies",
        "malayalam": "https://timesofindia.indiatimes.com/entertainment/latest-new-movies/malayalam-movies",
        "hindi":     "https://timesofindia.indiatimes.com/entertainment/latest-new-movies/hindi-movies",
        "english":   "https://timesofindia.indiatimes.com/entertainment/latest-new-movies/english-movies",
        "telugu":    "https://timesofindia.indiatimes.com/entertainment/latest-new-movies/telugu-movies",
        "kannada":   "https://timesofindia.indiatimes.com/entertainment/latest-new-movies/kannada-movies",
    },
    "91mobiles": {
        "ott":    "https://www.91mobiles.com/entertainment/ott-release-this-week",
        "series": "https://www.91mobiles.com/entertainment/best-web-series",
    },
    "1tamilmv": "https://www.1tamilmv.lease/",
}

TARGET_LANGUAGES = ["Tamil", "Malayalam", "Hindi", "English", "Telugu", "Kannada"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TOI_PLACEHOLDER_MSID = "61914123"

GENRE_KEYWORDS = [
    "Action", "Drama", "Comedy", "Romance", "Thriller", "Horror",
    "Sci-Fi", "Fantasy", "Adventure", "Crime", "Mystery",
    "Biography", "Animation", "Family", "Musical", "War",
    "History", "Sport", "Documentary", "Western", "Period",
]


# ═══════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════

def get_soup(url, timeout=20):
    """Fetch page using requests (no JS rendering)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        if resp.status_code == 200:
            return BeautifulSoup(resp.content, "html.parser")
        print(f"  [WARN] {url} -> HTTP {resp.status_code}")
    except Exception as e:
        print(f"  [ERROR] {url}: {e}")
    return None


def get_soup_chrome(url, wait_seconds=8):
    """Fetch page using headless Chrome (with JavaScript rendering)."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError:
        print("  [INFO] Selenium not installed, falling back to requests")
        return get_soup(url)

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=en-US")
    options.add_argument(f"--user-agent={HEADERS['User-Agent']}")

    try:
        driver = webdriver.Chrome(options=options)
        driver.get(url)
        time.sleep(wait_seconds)
        html = driver.page_source
        driver.quit()
        return BeautifulSoup(html, "html.parser")
    except Exception as e:
        print(f"  [WARN] Chrome failed for {url}: {e}")
        return get_soup(url)


def clean_text(text):
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()


def is_placeholder_image(url):
    if TOI_PLACEHOLDER_MSID in url:
        return True
    if "no-image.png" in url:
        return True
    return False


# ═══════════════════════════════════════════════════════════════
# TIMES OF INDIA — uses Chrome
# Extracts: image, title, rating, language, genre, duration, date release
# In the order as they appear on the website
# ═══════════════════════════════════════════════════════════════

def scrape_toi_page(lang, page_url):
    """
    Scrape TOI page using Chrome.
    Extract ALL fields from each movie card in website order.
    """
    print(f"  -> Chrome loading: {page_url}")
    soup = get_soup_chrome(page_url)
    if not soup:
        return []

    lang_lower = lang.lower()
    results = []
    seen_urls = set()

    # Find all <a> tags linking to movie detail pages for this language
    # (in the order they appear on the page)
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if f"/{lang_lower}/movie-details/" not in href:
            continue
        if "/movieshow/" not in href:
            continue

        full_url = href if href.startswith("http") else f"https://timesofindia.indiatimes.com{href}"
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        # Find card container: go up from <a> to find parent with <img>
        card = a
        for _ in range(6):
            if not card.parent:
                break
            card = card.parent
            if card.find("img"):
                break

        # ── Extract all fields ──
        item = {
            "title": "",
            "language": lang,
            "source": "Times of India",
            "category": "Movie",
            "link": full_url,
            "image": "",
            "rating": "",
            "genre": "",
            "duration": "",
            "release_date": "",
            "description": "",
        }

        # ── Title ──
        title = clean_text(a.get_text())
        if not title or len(title) < 2:
            for tag_name in ["h2", "h3", "h4", "h5"]:
                h = card.find(tag_name)
                if h:
                    title = clean_text(h.get_text())
                    if title and len(title) > 2:
                        break
        if not title:
            title = a.get("title", "")
        if not title:
            img_tag = card.find("img")
            if img_tag:
                title = img_tag.get("alt", "")
        if not title:
            slug = ""
            if "/movie-details/" in full_url:
                slug = full_url.split("/movie-details/")[-1].split("/")[0]
            title = slug.replace("-", " ").title()

        if not title or len(title) < 2:
            continue
        skip = {"english", "hindi", "tamil", "malayalam", "telugu", "kannada",
                "movie reviews", "movie details", "movies", "latest movies"}
        if title.lower() in skip:
            continue

        item["title"] = title

        # ── Image ──
        img_tag = card.find("img")
        if img_tag:
            src = img_tag.get("data-src") or img_tag.get("src") or ""
            if src and not is_placeholder_image(src):
                item["image"] = src
        if not item["image"]:
            msid_match = re.search(r'/(\d+)\.cms', full_url)
            if msid_match:
                msid = msid_match.group(1)
                item["image"] = f"https://static.toiimg.com/thumb/msid-{msid},width-420,height-350/{msid}.jpg"

        # ── Card text for parsing remaining fields ──
        card_text = card.get_text(" | ", strip=True)

        # ── Rating ──
        for pattern in [r'(\d\.\d)\s*/\s*5', r'★\s*(\d\.\d)',
                        r'Rating:?\s*(\d\.\d)', r'(\d\.\d)']:
            m = re.search(pattern, card_text, re.I)
            if m:
                val = float(m.group(1))
                if 0 <= val <= 10:
                    item["rating"] = m.group(1)
                    break

        # ── Genre ──
        found_genres = [g for g in GENRE_KEYWORDS if g.lower() in card_text.lower()]
        if found_genres:
            item["genre"] = ", ".join(found_genres)

        # ── Duration ──
        dur = re.search(r'(\d+)\s*hr[s]?\s*(\d+)?\s*min[s]?', card_text, re.I)
        if dur:
            h = dur.group(1)
            m = dur.group(2) or "0"
            item["duration"] = f"{h}h {m}m"
        else:
            dur = re.search(r'(\d+)\s*hr[s]?', card_text, re.I)
            if dur:
                item["duration"] = f"{dur.group(1)}h"
            else:
                dur = re.search(r'(\d+)\s*min[s]?', card_text, re.I)
                if dur:
                    item["duration"] = f"{dur.group(1)}min"

        # ── Release date ──
        for pat in [r'(\d{1,2}\s+\w{3,9}\s+20\d{2})',
                    r'(\w{3,9}\s+\d{1,2},?\s+20\d{2})']:
            dm = re.search(pat, card_text)
            if dm:
                item["release_date"] = dm.group(1)
                break

        results.append(item)

    return results


# ═══════════════════════════════════════════════════════════════
# 91MOBILES — uses requests
# ═══════════════════════════════════════════════════════════════

def extract_91mobiles_item(card, source_label, category):
    item = {
        "title": "", "language": "", "release_date": "",
        "image": "", "description": "", "link": "",
        "source": source_label, "category": category,
    }
    h3 = card.find("h3")
    if h3:
        a = h3.find("a", href=True)
        if a:
            item["title"] = clean_text(a.get_text())
            href = a.get("href", "")
            item["link"] = href if href.startswith("http") else f"https://www.91mobiles.com{href}"
        else:
            item["title"] = clean_text(h3.get_text())
    if not item["link"]:
        dh = card.get("data-href", "")
        if dh:
            item["link"] = dh if dh.startswith("http") else f"https://www.91mobiles.com{dh}"
    imdb_box = card.find("div", class_="imdb_box")
    if imdb_box:
        p = imdb_box.find("p")
        if p:
            text = clean_text(p.get_text())
            parts = text.split("|")
            if parts:
                item["language"] = parts[0].strip()
            if len(parts) > 1:
                item["release_date"] = parts[1].strip()
            else:
                item["release_date"] = text
    img_box = card.find("div", class_="img_box")
    if img_box:
        img = img_box.find("img")
        if img:
            src = img.get("data-src") or img.get("src") or ""
            if src and not is_placeholder_image(src):
                item["image"] = src
    desc_div = card.find("div", class_="mov_desc")
    if desc_div:
        item["description"] = clean_text(desc_div.get_text())
    return item


def is_within_this_week(date_str):
    if not date_str:
        return False
    text = date_str.strip()
    text_lower = text.lower()
    if any(kw in text_lower for kw in ["today", "yesterday", "this week"]):
        return True
    for fmt in ["%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"]:
        try:
            dt = datetime.strptime(text, fmt)
            return 0 <= (datetime.now() - dt).days <= 7
        except ValueError:
            continue
    return False


def match_language(lang_str):
    lang_lower = lang_str.lower()
    for tl in TARGET_LANGUAGES:
        if tl.lower() in lang_lower:
            return tl
    return None


def scrape_91mobiles_ott(url):
    soup = get_soup(url)
    if not soup:
        return []
    results = []
    for card in soup.find_all("div", class_="pro_item"):
        item = extract_91mobiles_item(card, "91Mobiles OTT", "OTT Release")
        if not item["title"]:
            continue
        matched = match_language(item["language"])
        if matched:
            item["language"] = matched
            results.append(item)
    return results


def scrape_91mobiles_series(url):
    soup = get_soup(url)
    if not soup:
        return []
    results = []
    for card in soup.find_all("div", class_="pro_item"):
        item = extract_91mobiles_item(card, "91Mobiles Series", "Web Series")
        if not item["title"]:
            continue
        if not is_within_this_week(item["release_date"]):
            continue
        matched = match_language(item["language"])
        if matched:
            item["language"] = matched
            results.append(item)
    return results


# ═══════════════════════════════════════════════════════════════
# 1TAMILMV — first 25 titles only
# ═══════════════════════════════════════════════════════════════

def scrape_1tamilmv(url):
    soup = get_soup(url)
    if not soup:
        return []
    results = []
    seen = set()
    for strong in soup.find_all("strong"):
        if len(results) >= 25:
            break
        a = strong.find("a", href=True)
        if not a:
            continue
        href = a.get("href", "")
        if "/forums/topic/" not in href:
            continue
        title = clean_text(a.get_text())
        if not title or len(title) < 3:
            continue
        if title.upper() == title and len(title) < 60 and not any(c.isdigit() for c in title):
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "title": title, "language": "Tamil", "source": "1TamilMV",
            "category": "Movie Release", "link": href,
            "image": "", "description": "", "release_date": "",
        })
    return results


# ═══════════════════════════════════════════════════════════════
# RSS FEED BUILDER — image in enclosure + description + content
# ═══════════════════════════════════════════════════════════════

def build_rss(items, title, filename, channel_link, description=""):
    fg = FeedGenerator()
    fg.id(channel_link)
    fg.title(title)
    fg.author({"name": "Entertainment Scraper"})
    fg.link(href=channel_link, rel="alternate")
    fg.description(description or "Automated entertainment feed")
    fg.language("en")

    seen = set()
    for item in items:
        key = (item["title"].lower(), item.get("source", ""))
        if key in seen:
            continue
        seen.add(key)

        fe = fg.add_entry()
        fe.id(item.get("link") or item["title"])

        prefix = []
        if item.get("language"):
            prefix.append(f"[{item['language']}]")
        if item.get("category"):
            prefix.append(f"[{item['category']}]")
        fe.title(f"{' '.join(prefix)} {item['title']}".strip())

        if item.get("link"):
            fe.link(href=item["link"])

        # HTML content with image + all fields
        html_parts = []
        if item.get("image"):
            html_parts.append(
                f'<img src="{item["image"]}" alt="{item["title"]}" '
                f'style="max-width:300px;float:left;margin:0 10px 10px 0;border-radius:6px;" />'
            )
        html_parts.append('<table style="border-collapse:collapse;margin-bottom:8px;">')
        for label, k in [("Source", "source"), ("Language", "language"),
                         ("Category", "category"), ("Rating", "rating"),
                         ("Genre", "genre"), ("Duration", "duration"),
                         ("Release Date", "release_date")]:
            val = item.get(k)
            if val:
                html_parts.append(
                    f'<tr><td style="padding:2px 8px;"><b>{label}</b></td>'
                    f'<td style="padding:2px 8px;">{val}</td></tr>'
                )
        html_parts.append('</table>')
        if item.get("description"):
            html_parts.append(f'<p>{item["description"]}</p>')

        html_content = "".join(html_parts)
        fe.description(html_content)
        try:
            fe.content(html_content, type="html")
        except Exception:
            pass
        if item.get("image"):
            try:
                fe.enclosure(item["image"], "0", "image/jpeg")
            except Exception:
                pass
        fe.pubDate(datetime.now(timezone.utc))

    fg.rss_file(filename)
    print(f"  -> {filename} ({len(seen)} items)")


# ═══════════════════════════════════════════════════════════════
# MAIN — Sequential: fetch one URL, store, generate, clear, next
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  Entertainment RSS Feed Generator")
    print("  TOI: Chrome | 91Mobiles: requests | 1TamilMV: requests")
    print("  Sequential fetch — one URL at a time")
    print("=" * 60)

    # Step 1: TOI (Chrome) — one language page at a time
    print("\n[Step 1] Times of India (6 languages, Chrome)")
    for lang_key, url in LINKS["toi"].items():
        lang = lang_key.title()
        print(f"\n  -> Fetching TOI {lang} via Chrome...")
        items = scrape_toi_page(lang, url)
        build_rss(items, f"Times of India -- {lang} Movies",
                  f"feed_toi_{lang_key}.xml", url,
                  f"Latest {lang} movies from Times of India")
        print(f"     {len(items)} movies scraped")
        del items  # clear before next fetch

    # Step 2: 91Mobiles OTT
    print(f"\n[Step 2] 91Mobiles OTT This Week")
    ott_url = LINKS["91mobiles"]["ott"]
    print(f"  -> Fetching {ott_url}...")
    ott_items = scrape_91mobiles_ott(ott_url)
    print(f"     {len(ott_items)} total items")
    for lang in TARGET_LANGUAGES:
        lang_items = [i for i in ott_items if i["language"] == lang]
        build_rss(lang_items, f"91Mobiles OTT -- {lang}",
                  f"feed_91mobiles_ott_{lang.lower()}.xml", ott_url,
                  f"OTT releases this week -- {lang} only")
        print(f"     {lang}: {len(lang_items)} items")
        del lang_items
    del ott_items

    # Step 3: 91Mobiles Series
    print(f"\n[Step 3] 91Mobiles Best Web Series (this week)")
    series_url = LINKS["91mobiles"]["series"]
    print(f"  -> Fetching {series_url}...")
    series_items = scrape_91mobiles_series(series_url)
    print(f"     {len(series_items)} total items")
    for lang in TARGET_LANGUAGES:
        lang_items = [i for i in series_items if i["language"] == lang]
        build_rss(lang_items, f"91Mobiles Series -- {lang}",
                  f"feed_91mobiles_series_{lang.lower()}.xml", series_url,
                  f"Best web series this week -- {lang} only")
        print(f"     {lang}: {len(lang_items)} items")
        del lang_items
    del series_items

    # Step 4: 1TamilMV
    print(f"\n[Step 4] 1TamilMV (first 25 titles)")
    tmv_url = LINKS["1tamilmv"]
    print(f"  -> Fetching {tmv_url}...")
    tmv_items = scrape_1tamilmv(tmv_url)
    build_rss(tmv_items, "1TamilMV -- Latest Releases",
              "feed_1tamilmv.xml", tmv_url,
              "First 25 latest movie release titles from 1TamilMV")
    print(f"     {len(tmv_items)} titles")
    del tmv_items

    print(f"\n{'=' * 60}")
    print("  Done! 19 individual feeds generated.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
