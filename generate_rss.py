#!/usr/bin/env python3
"""
Multi-Website RSS Feed Generator
Generates SEPARATE feeds for each website, language, and category.
Sources: Times of India (4 langs), 91Mobiles (OTT + Web Series), 1TamilMV (25 titles)
"""

import json
import re
import sys
import time
import hashlib
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
from urllib.parse import urljoin

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

TARGET_LANGUAGES = ["Tamil", "Malayalam", "Hindi", "English"]
TOI_BASE = "https://timesofindia.indiatimes.com"
NINETYONE_BASE = "https://www.91mobiles.com"


def fetch_page(url, retries=3, timeout=20):
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=timeout)
            if response.status_code == 200:
                return response.text
        except Exception as e:
            print(f"[WARN] Attempt {attempt+1}/{retries} failed for {url}: {e}", file=sys.stderr)
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
    return None


def get_soup(url):
    html = fetch_page(url)
    if html:
        return BeautifulSoup(html, "lxml")
    return None


# ──────────────────────────────────────────────────────────
# SCRAPER 1: Times of India (4 languages)
# ──────────────────────────────────────────────────────────

def scrape_toi():
    toi_urls = {
        "Tamil": f"{TOI_BASE}/entertainment/latest-new-movies/tamil-movies",
        "Malayalam": f"{TOI_BASE}/entertainment/latest-new-movies/malayalam-movies",
        "Hindi": f"{TOI_BASE}/entertainment/latest-new-movies/hindi-movies",
        "English": f"{TOI_BASE}/entertainment/latest-new-movies/english-movies",
    }
    all_results = {}

    for lang, url in toi_urls.items():
        soup = get_soup(url)
        if not soup:
            continue

        movie_urls = []
        for script in soup.find_all("script", type="application/ld+json"):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(data, dict) and data.get("@type") == "ItemList":
                for item in data.get("itemListElement", []):
                    if isinstance(item, dict):
                        u = item.get("url", "")
                        if u:
                            if u.startswith("http://"):
                                u = "https://" + u[len("http://"):]
                            elif not u.startswith("http"):
                                u = urljoin(TOI_BASE, u)
                            movie_urls.append(u)

        cards_by_url = {}
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "/movie-details/" not in href or "/movieshow/" not in href:
                continue
            full_url = urljoin(TOI_BASE, href) if not href.startswith("http") else href
            if full_url.startswith("http://"):
                full_url = "https://" + full_url[len("http://"):]
            if full_url in cards_by_url:
                continue

            parent = a
            for _ in range(6):
                if parent.parent and parent.parent.name not in ("body", "html"):
                    parent = parent.parent
                else:
                    break

            title = ""
            heading = parent.find(["h1", "h2", "h3", "h4"])
            if heading:
                title = heading.get_text(strip=True)
            if not title:
                title = a.get_text(strip=True)
            if not title:
                try:
                    title = href.split("/movie-details/")[1].split("/")[0].replace("-", " ").title()
                except (IndexError, AttributeError):
                    title = "Untitled"
            if len(title) < 2:
                continue

            image_url = ""
            img_tag = parent.find("img")
            if img_tag:
                image_url = (
                    img_tag.get("src")
                    or img_tag.get("data-src")
                    or img_tag.get("data-original")
                    or img_tag.get("data-lazy-src")
                    or ""
                )
                if image_url and not image_url.startswith("http"):
                    image_url = urljoin(TOI_BASE, image_url)

            card_text = parent.get_text(separator=" | ", strip=True)

            rating_match = re.search(r"(?:Critic'?s?\s*Rating|Rating)\s*[:\s]*([\d.]+)", card_text, re.I)
            rating = rating_match.group(1) if rating_match else "N/A"

            genre_match = re.search(
                r"Genre\s*[:\s]*([A-Za-z,\s/\-]+?)(?=\s*(?:Language|Duration|Release|Critic|Rating|\||$))",
                card_text, re.I,
            )
            genre = genre_match.group(1).strip().rstrip(",").strip() if genre_match else "Cinema"
            if not genre:
                genres_list = ("Drama","Action","Comedy","Thriller","Romance","Adventure","Horror","Sci-Fi","Family","Fantasy","Crime","Mystery","Biography","Animation","Documentary","Musical","War","Sport","Historical","Period","Political")
                pattern = r"\b(" + "|".join(genres_list) + r")(?:\s*,\s*(?:" + "|".join(genres_list) + r"))*\b"
                gm = re.search(pattern, card_text, re.I)
                genre = gm.group(0).strip() if gm else "Cinema"

            duration_match = re.search(
                r"Duration\s*[:\s]*(\d+\s*(?:hrs?|hours?|h)\s*\d+\s*(?:mins?|m)|\d+\s*(?:hrs?|hours?|h)|\d+\s*mins?)",
                card_text, re.I,
            )
            if not duration_match:
                duration_match = re.search(r"\b(\d+\s*(?:hrs?|hours?|h)\s*\d+\s*(?:mins?|m))\b", card_text, re.I)
            if not duration_match:
                duration_match = re.search(r"\b(\d+\s*(?:hrs?|hours?|h))\b", card_text, re.I)
            if not duration_match:
                duration_match = re.search(r"\b(\d+\s*mins?)\b", card_text, re.I)
            duration = duration_match.group(1).strip() if duration_match else "N/A"

            months = ("Jan(?:uary)?","Feb(?:ruary)?","Mar(?:ch)?","Apr(?:il)?","May","Jun(?:e)?","Jul(?:y)?","Aug(?:ust)?","Sep(?:tember)?","Oct(?:ober)?","Nov(?:ember)?","Dec(?:ember)?")
            months_pat = "|".join(months)
            release_match = re.search(rf"(?:Release\s*Date|Released|Releasing)\s*[:\s]*(\d{{1,2}}\s+(?:{months_pat})\s+\d{{4}})", card_text, re.I)
            if not release_match:
                release_match = re.search(rf"\b(\d{{1,2}}\s+(?:{months_pat})\s+\d{{4}})\b", card_text, re.I)
            if not release_match:
                release_match = re.search(rf"\b((?:{months_pat})\s+\d{{1,2}},?\s+\d{{4}})\b", card_text, re.I)
            if not release_match:
                release_match = re.search(r"\b(20\d{2})\b", card_text)
            release_date = release_match.group(1).strip() if release_match else "Recent"

            cards_by_url[full_url] = {
                "title": title,
                "image": image_url,
                "text": card_text,
                "rating": rating,
                "genre": genre,
                "duration": duration,
                "release_date": release_date,
            }

        results = []
        seen = set()
        for u in movie_urls:
            if u in seen:
                continue
            seen.add(u)
            card = cards_by_url.get(u, {})
            if not card:
                try:
                    slug = u.split("/movie-details/")[-1].split("/")[0]
                    title = slug.replace("-", " ").title()
                except (IndexError, AttributeError):
                    title = "Untitled"
                card = {"title": title, "image": "", "text": "", "rating": "N/A", "genre": "N/A", "duration": "N/A", "release_date": "Recent"}
            results.append({
                "title": card.get("title", "Untitled"),
                "link": u,
                "image": card.get("image", ""),
                "language": lang,
                "source": "Times of India",
                "category": "Movies",
                "rating": card.get("rating", "N/A"),
                "genre": card.get("genre", "N/A"),
                "duration": card.get("duration", "N/A"),
                "release_date": card.get("release_date", "Recent"),
            })

        if not results:
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                if "/movie-details/" not in href:
                    continue
                full_url = urljoin(TOI_BASE, href) if not href.startswith("http") else href
                title = a.get_text(strip=True)
                if title and len(title) > 2:
                    results.append({
                        "title": title, "link": full_url, "image": "",
                        "language": lang, "source": "Times of India", "category": "Movies",
                        "rating": "N/A", "genre": "N/A", "duration": "N/A", "release_date": "Recent",
                    })

        all_results[lang] = results

    return all_results


# ──────────────────────────────────────────────────────────
# SCRAPER 2: 91Mobiles (OTT + Web Series)
# ──────────────────────────────────────────────────────────

def is_released_this_week(date_text):
    if not date_text:
        return False
    text_lower = date_text.lower()
    if any(kw in text_lower for kw in ["today", "yesterday", "days ago", "this week"]):
        return True
    months = ("Jan(?:uary)?","Feb(?:ruary)?","Mar(?:ch)?","Apr(?:il)?","May","Jun(?:e)?","Jul(?:y)?","Aug(?:ust)?","Sep(?:tember)?","Oct(?:ober)?","Nov(?:ember)?","Dec(?:ember)?")
    months_pat = "|".join(months)
    match = re.search(rf"(\d{{1,2}})\s+({months_pat})\s+(\d{{4}})", date_text, re.I)
    if match:
        try:
            month_short = match.group(2)[:3]
            date_str = f"{match.group(1)} {month_short} {match.group(3)}"
            release_date = datetime.strptime(date_str, "%d %b %Y")
            days_diff = (datetime.now() - release_date).days
            if 0 <= days_diff <= 7:
                return True
        except ValueError:
            pass
    return False


def scrape_91mobiles(url, feed_type, require_this_week=False):
    soup = get_soup(url)
    all_results = {lang: [] for lang in TARGET_LANGUAGES}
    if not soup:
        return all_results

    cards = soup.find_all("div", class_=re.compile(r"pro_item|card_box"))
    if not cards:
        cards = soup.find_all("div", class_=lambda x: x and "pro_item" in str(x))

    for card in cards:
        try:
            title_tag = card.find("h3")
            title = ""
            link = ""
            if title_tag:
                a_tag = title_tag.find("a", href=True)
                if a_tag:
                    title = a_tag.get_text(strip=True)
                    href = a_tag.get("href", "")
                    link = urljoin(NINETYONE_BASE, href) if href.startswith("/") else href
                else:
                    title = title_tag.get_text(strip=True)
            if not title:
                a_tag = card.find("a", href=True)
                if a_tag:
                    title = a_tag.get("title", "") or a_tag.get_text(strip=True)
                    href = a_tag.get("href", "")
                    link = urljoin(NINETYONE_BASE, href) if href.startswith("/") else href
            if not title or len(title) < 2:
                continue

            data_link = card.find(attrs={"data-href": True})
            if data_link and not link:
                href = data_link.get("data-href", "")
                link = href if href.startswith("http") else urljoin(NINETYONE_BASE, href)

            meta_text = ""
            meta_tag = card.find("p", class_=re.compile(r"d-in-block|f-s-m"))
            if meta_tag:
                meta_text = meta_tag.get_text(strip=True)
            if not meta_text:
                meta_text = card.get_text(separator=" | ", strip=True)

            detected_lang = None
            for lang in TARGET_LANGUAGES:
                if lang.lower() in meta_text.lower():
                    detected_lang = lang
                    break
            if not detected_lang:
                continue

            date_str = ""
            parts = meta_text.split("|")
            if len(parts) >= 2:
                date_str = parts[-1].strip()
            else:
                months = ("Jan(?:uary)?","Feb(?:ruary)?","Mar(?:ch)?","Apr(?:il)?","May","Jun(?:e)?","Jul(?:y)?","Aug(?:ust)?","Sep(?:tember)?","Oct(?:ober)?","Nov(?:ember)?","Dec(?:ember)?")
                months_pat = "|".join(months)
                date_match = re.search(rf"(\d{{1,2}}\s+(?:{months_pat})\s+\d{{4}})", meta_text, re.I)
                if date_match:
                    date_str = date_match.group(1)

            if require_this_week:
                if not is_released_this_week(date_str or meta_text):
                    continue

            image_url = ""
            img_tag = card.find("img")
            if img_tag:
                image_url = img_tag.get("data-src") or img_tag.get("src") or ""
                if image_url and image_url.endswith("no-image.png"):
                    image_url = img_tag.get("data-src", "")
                if image_url and not image_url.startswith("http"):
                    image_url = urljoin(NINETYONE_BASE, image_url)

            description = ""
            desc_tag = card.find("div", class_=re.compile(r"mov_desc"))
            if desc_tag:
                description = desc_tag.get_text(strip=True)

            all_results[detected_lang].append({
                "title": title,
                "link": link or url,
                "image": image_url,
                "language": detected_lang,
                "source": "91Mobiles",
                "category": feed_type,
                "rating": "N/A",
                "genre": "N/A",
                "duration": "N/A",
                "release_date": date_str or "N/A",
                "description": description,
            })
        except Exception as e:
            print(f"[WARN] 91mobiles card parse error: {e}", file=sys.stderr)
            continue

    return all_results


# ──────────────────────────────────────────────────────────
# SCRAPER 3: 1TamilMV (25 titles)
# ──────────────────────────────────────────────────────────

def scrape_1tamilmv():
    url = "https://www.1tamilmv.fi/"
    soup = get_soup(url)
    results = []
    if not soup:
        return results

    seen_titles = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "/forums/topic/" not in href:
            continue
        title = a.get_text(strip=True)
        if not title or len(title) < 3:
            continue
        if any(nav in title.lower() for nav in ["sign in","browse","home","forums","leaderboard","movies","tamil","telugu","hindi","malayalam","kannada","english","members lounge","post & share","request section","languages","watch online"]):
            continue
        if title in seen_titles:
            continue
        full_link = href
        if not full_link.startswith("http"):
            full_link = "https://www.1tamilmv.lease" + href if href.startswith("/") else href

        seen_titles.add(title)
        results.append({
            "title": title,
            "link": full_link,
            "image": "",
            "language": "Tamil",
            "source": "1TamilMV",
            "category": "Download",
            "rating": "N/A",
            "genre": "N/A",
            "duration": "N/A",
            "release_date": "N/A",
            "description": "",
        })
        if len(results) >= 25:
            break

    return results


# ──────────────────────────────────────────────────────────
# RSS BUILDER
# ──────────────────────────────────────────────────────────

def html_escape(s):
    if not s:
        return ""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_rss(items, feed_title, feed_filename):
    if not items:
        print(f"[SKIP] No items for {feed_filename}")
        return

    fg = FeedGenerator()
    fg.id(feed_filename)
    fg.title(feed_title)
    fg.author({"name": "Multi-Scraper", "email": "noreply@github.com"})
    fg.link(href="https://github.com", rel="alternate")
    fg.description("Automated RSS feed for movies, OTT releases, web series, and 1TamilMV titles.")
    fg.language("en")

    seen = set()
    for item in items:
        key = (item["title"], item.get("source", ""))
        if key in seen:
            continue
        seen.add(key)

        try:
            fe = fg.add_entry()
            fe.id(item.get("link", "") or f"{feed_filename}#{hashlib.md5(item['title'].encode()).hexdigest()}")
            fe.title(item["title"])
            if item.get("link"):
                fe.link(href=item["link"])

            # Format description to include image at the beginning, similar to TOI format
            safe_title = html_escape(item["title"])
            safe_image = html_escape(item.get("image", ""))
            safe_rating = html_escape(str(item.get("rating", "N/A")))
            safe_genre = html_escape(str(item.get("genre", "N/A")))
            safe_duration = html_escape(str(item.get("duration", "N/A")))
            safe_release = html_escape(str(item.get("release_date", "N/A")))
            safe_lang = html_escape(item.get("language", "Tamil"))
            safe_desc = html_escape(item.get("description", ""))
            safe_link = html_escape(item.get("link", ""))
            safe_source = html_escape(item.get("source", ""))
            safe_cat = html_escape(item.get("category", "Movie"))

            image_html = ""
            if item.get("image"):
                image_html = f'&lt;img border="0" hspace="10" align="left" style="margin-top:3px;margin-right:5px;" src="{safe_image}" /&gt;'

            content_html = (
                f"<ul>"
                f"<li><b>Title:</b> {safe_title}</li>"
                f"<li><b>Language:</b> {safe_lang}</li>"
                f"<li><b>Source:</b> {safe_source}</li>"
                f"<li><b>Category:</b> {safe_cat}</li>"
                f"<li><b>Rating:</b> {safe_rating}</li>"
                f"<li><b>Genre:</b> {safe_genre}</li>"
                f"<li><b>Duration:</b> {safe_duration}</li>"
                f"<li><b>Release Date:</b> {safe_release}</li>"
                f"</ul>"
            )
            if safe_desc:
                content_html += f"<p>{safe_desc}</p>"

            # Combine image and content for the description tag
            full_description = f"{image_html}<![CDATA[{content_html}]]>"
            
            fe.description(full_description)
            
            # Add enclosure for image if available (helps RSS readers display thumbnails)
            if item.get("image"):
                fe.enclosure(url=item["image"], type="image/jpeg")
                
            fe.pubDate(datetime.now(timezone.utc))
        except Exception as e:
            print(f"[WARN] Entry error: {e}", file=sys.stderr)
            continue

    try:
        fg.rss_file(feed_filename)
        print(f"[OK] {feed_filename} ({len(seen)} items)")
    except Exception as e:
        print(f"[ERROR] {feed_filename}: {e}", file=sys.stderr)

# ──────────────────────────────────────────────────────────
# MAIN — generates ONLY separate feeds per source/language/category
# ──────────────────────────────────────────────────────────

def main():
    # ── TOI (per-language feeds) ──
    print("[INFO] Scraping Times of India...")
    toi_by_lang = scrape_toi()
    for lang in TARGET_LANGUAGES:
        items = toi_by_lang.get(lang, [])
        build_rss(items, f"TOI {lang} Movies", f"feed_toi_{lang.lower()}.xml")

    # ── 91Mobiles OTT This Week (per-language feeds) ──
    print("[INFO] Scraping 91Mobiles OTT This Week...")
    ott_by_lang = scrape_91mobiles(
        "https://www.91mobiles.com/entertainment/ott-release-this-week",
        feed_type="OTT Release",
        require_this_week=False,
    )
    for lang in TARGET_LANGUAGES:
        items = ott_by_lang.get(lang, [])
        build_rss(items, f"91Mobiles {lang} OTT This Week", f"feed_91mobiles_ott_{lang.lower()}.xml")

    # ── 91Mobiles Best Web Series This Week (per-language feeds) ──
    print("[INFO] Scraping 91Mobiles Best Web Series (this week)...")
    series_by_lang = scrape_91mobiles(
        "https://www.91mobiles.com/entertainment/best-web-series",
        feed_type="Web Series",
        require_this_week=True,
    )
    for lang in TARGET_LANGUAGES:
        items = series_by_lang.get(lang, [])
        build_rss(items, f"91Mobiles {lang} Web Series This Week", f"feed_91mobiles_series_{lang.lower()}.xml")

    # ── 1TamilMV (single feed) ──
    print("[INFO] Scraping 1TamilMV...")
    tmv_items = scrape_1tamilmv()
    build_rss(tmv_items, "1TamilMV Latest Downloads", "feed_1tamilmv.xml")

    print("\n[DONE] All separate feeds generated.")


if __name__ == "__main__":
    main()
