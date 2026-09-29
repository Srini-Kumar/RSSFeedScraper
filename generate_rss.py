#!/usr/bin/env python3
"""
Entertainment RSS Feed Generator
  - Times of India  → movie reviews per language
  - 91Mobiles       → OTT releases per language + web series (last 7 days) per language
  - 1TamilMV        → latest releases
"""

import os, re, json, time, logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s',
                    datefmt='%H:%M:%S')
log = logging.getLogger("rss")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TOI_BASE     = "https://timesofindia.indiatimes.com"
MOBILES_BASE = "https://www.91mobiles.com"
TAMILMV_URLS = ["https://www.1tamilmv.to/", "https://www.1tamilmv.to/index.php"]

TOI_LANGS     = ["hindi","tamil","telugu","malayalam","kannada","english","bengali","marathi"]
M_LANGS       = ["hindi","english","tamil","telugu","malayalam","kannada"]

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}
TIMEOUT = 25
RETRIES = 3
DELAY   = 0.7

# ── session so cookies persist ───────────────────────────────────────────────
_session = requests.Session()
_session.headers.update(HEADERS)

# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def http_get(url):
    for i in range(RETRIES):
        try:
            r = _session.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            return r.text
        except Exception as e:
            log.warning("  GET fail [%d/%d] %s → %s", i+1, RETRIES, url, e)
            if i < RETRIES - 1:
                time.sleep(2 + i*2)
    return ""

def txt(node):
    if node is None: return ""
    return re.sub(r'\s+', ' ', node.get_text()).strip()

def parse_date(s):
    if not s: return None
    s = re.sub(r'\s+', ' ', str(s)).strip()
    for fmt in ("%d %b %Y","%d %B %Y","%B %d, %Y","%b %d, %Y",
                "%Y-%m-%d","%d-%m-%Y","%d/%m/%Y",
                "%d %b %Y, %I:%M %p","%d %B %Y, %I:%M %p",
                "%Y-%m-%dT%H:%M:%S","%Y-%m-%dT%H:%M:%SZ",
                "%a, %d %b %Y %H:%M:%S"):
        try: return datetime.strptime(s, fmt)
        except ValueError: pass
    m = re.search(r'(\d{1,2}\s+\w+\s+20\d{2})', s)
    if m:
        for fmt in ("%d %b %Y","%d %B %Y"):
            try: return datetime.strptime(m.group(1), fmt)
            except ValueError: pass
    return None

# ═══════════════════════════════════════════════════════════════════════════════
# FEED BUILDERS
# ═══════════════════════════════════════════════════════════════════════════════

def new_feed(title, desc, link, lang="en"):
    fg = FeedGenerator()
    fg.id(link)
    fg.title(title)
    fg.link(href=link, rel="alternate")
    fg.description(desc)
    fg.language(lang)
    fg.lastBuildDate(datetime.now(timezone.utc))
    fg.docs("http://www.rssboard.org/rss-specification")
    return fg

def build_desc_html(item):
    """Build clean HTML — NO pre-escaping, feedgen/lxml escapes once."""
    p = []
    img = item.get("image")
    if img:
        p.append(f'<img src="{img}" alt="{item.get("title","")}" '
                 f'style="max-width:300px;float:left;margin:0 10px 10px 0;'
                 f'border-radius:6px;" />')
    rows = []
    for label, key in [("Language","language"),("Source","source"),
                        ("Category","category"),("Rating","rating"),
                        ("Genre","genre"),("Duration","duration"),
                        ("Release Date","release_date")]:
        v = item.get(key)
        if v and str(v).strip() and str(v).strip() != "N/A":
            rows.append(f"<tr><td><b>{label}</b></td><td>{v}</td></tr>")
    if rows:
        p.append('<table style="border-collapse:collapse;margin-bottom:8px;">'
                  + "".join(rows) + "</table>")
    d = item.get("description")
    if d:
        p.append(f"<p>{d}</p>")
    return "".join(p)

def add_entry(fg, item):
    fe = fg.add_entry()
    fe.id(item.get("guid") or item.get("link") or item.get("title",""))
    fe.title(item.get("title","Untitled"))
    if item.get("link"):
        fe.link(href=item["link"])
    # ★ Pass RAW HTML — no html.escape(), no manual CDATA
    fe.description(build_desc_html(item))
    if item.get("image"):
        try: fe.enclosure(item["image"], "0", "image/jpeg")
        except Exception: pass
    pd = item.get("pub_date") or item.get("release_date")
    if pd:
        dt = parse_date(pd) if isinstance(pd, str) else pd
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            fe.pubDate(dt)

def save_feed(fg, fname):
    fg.rss_file(os.path.join(BASE_DIR, fname))
    log.info("  ✓ %s (%d items)", fname, len(fg.entry()))

def save_empty(fname, title, desc, link):
    fg = new_feed(title, desc, link)
    save_feed(fg, fname)

# ═══════════════════════════════════════════════════════════════════════════════
# TOI
# ═══════════════════════════════════════════════════════════════════════════════

def scrape_toi():
    log.info("=" * 60)
    log.info("TOI Movies")
    log.info("=" * 60)
    for lang in TOI_LANGS:
        log.info("─ TOI %s", lang)
        try:
            items = _toi_lang(lang)
        except Exception as e:
            log.error("  TOI %s ERROR: %s", lang, e, exc_info=True)
            items = []
        fg = new_feed(
            f"Times of India — {lang.title()} Movies",
            f"Latest {lang} movie reviews from Times of India",
            f"{TOI_BASE}/entertainment/{lang}/movie-reviews", lang)
        for it in items:
            add_entry(fg, it)
        save_feed(fg, f"feed_toi_movies_{lang}.xml")

def _toi_lang(lang):
    urls = [
        f"{TOI_BASE}/entertainment/{lang}/movie-reviews",
        f"{TOI_BASE}/entertainment/{lang}/movies",
    ]
    html, page_url = "", ""
    for u in urls:
        log.info("  trying %s", u)
        html = http_get(u)
        if html and len(html) > 3000:
            page_url = u
            break
        time.sleep(0.5)
    if not html:
        log.error("  ✗ could not load TOI for %s", lang)
        return []

    soup = BeautifulSoup(html, "lxml")
    items, seen_titles = [], set()

    # ── Strategy A: parse listing cards ──
    # Find every anchor that links to a movie-details or movie-review page
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not ("movie-details" in href or "movie-review" in href):
            continue
        title = txt(a) or a.get("title","")
        if not title or len(title) < 2:
            # maybe parent has the title
            parent = a.find_parent(["div","li","article","td"])
            if parent:
                h = parent.find(["h3","h2","h4"])
                if h: title = txt(h)
        if not title or len(title) < 2:
            continue
        title = title.split("|")[0].strip()  # clean pipe-separated titles
        if title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        link = urljoin(TOI_BASE, href.split("?")[0])
        item = {"title": title, "link": link, "guid": link,
                "language": lang, "source": "Times of India",
                "category": "Movie Review"}

        # image & meta from parent
        parent = a.find_parent(["div","li","article","td","tr"])
        if parent:
            img = parent.find("img")
            if img:
                src = img.get("src") or img.get("data-src") or img.get("data-original")
                if src and "placeholder" not in src.lower() and "1x1" not in src:
                    item["image"] = src
            rt = parent.find(class_=re.compile(r"rating|score|star", re.I))
            if rt: item["rating"] = txt(rt)
            dt = parent.find(class_=re.compile(r"date|year|release", re.I))
            if dt: item["release_date"] = txt(dt)
            p = parent.find("p")
            if p: item["description"] = txt(p)
        else:
            img = a.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src: item["image"] = src
        items.append(item)

    # ── Strategy B: if few items, fetch detail pages ──
    if len(items) < 5:
        log.info("  only %d from listing — fetching detail pages", len(items))
        detail_links = [it["link"] for it in items if it.get("link")]
        # also try raw links we haven't visited
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "movie-details" in href or "movie-review" in href:
                full = urljoin(TOI_BASE, href.split("?")[0])
                if full not in detail_links:
                    detail_links.append(full)
        for link in detail_links[:20]:
            dh = http_get(link)
            if not dh: continue
            it = _toi_detail(dh, link, lang)
            if it and it.get("title") and it["title"].lower() not in seen_titles:
                seen_titles.add(it["title"].lower())
                items.append(it)
            time.sleep(DELAY)

    log.info("  → %d items for %s", len(items), lang)
    return items[:25]

def _toi_detail(html_text, url, lang):
    soup = BeautifulSoup(html_text, "lxml")
    item = {"language": lang, "source": "Times of India",
            "category": "Movie Review", "link": url, "guid": url}

    h1 = soup.find("h1")
    if h1:
        item["title"] = txt(h1).split("|")[0].strip()
    else:
        og = soup.find("meta", property="og:title")
        if og: item["title"] = og.get("content","").strip()
    if not item.get("title"): return None

    og_img = soup.find("meta", property="og:image")
    if og_img: item["image"] = og_img.get("content","")

    og_desc = soup.find("meta", property="og:description")
    if og_desc: item["description"] = og_desc.get("content","").strip()
    else:
        meta = soup.find("meta", attrs={"name":"description"})
        if meta: item["description"] = meta.get("content","").strip()

    rt = soup.find(class_=re.compile(r"rating|score|star", re.I))
    if rt: item["rating"] = txt(rt)

    for node in soup.find_all(["span","div","p","li"]):
        t = txt(node)
        if ":" in t and len(t) < 80:
            label, _, val = t.partition(":")
            ll, vv = label.strip().lower(), val.strip()
            if not vv: continue
            if "genre" in ll:        item["genre"] = vv
            elif "duration" in ll or "runtime" in ll: item["duration"] = vv
            elif "release" in ll:    item["release_date"] = vv
    return item

# ═══════════════════════════════════════════════════════════════════════════════
# 91MOBILES
# ═══════════════════════════════════════════════════════════════════════════════

# matches /entertainment/<slug>-<digits>  (detail pages, NOT section pages)
DETAIL_RE = re.compile(r'/entertainment/[\w-]+-\d{4,}', re.I)

def scrape_91mobiles():
    log.info("=" * 60)
    log.info("91Mobiles")
    log.info("=" * 60)

    # ── OTT releases ──
    for lang in M_LANGS:
        log.info("─ 91M OTT %s", lang)
        try:
            items = _91m_section("ott-releases", lang, "OTT Release", filter_days=None)
        except Exception as e:
            log.error("  OTT %s ERROR: %s", lang, e, exc_info=True)
            items = []
        fg = new_feed(
            f"91Mobiles — {lang.title()} OTT Releases This Week",
            f"Latest OTT releases in {lang} from 91Mobiles",
            f"{MOBILES_BASE}/entertainment/ott-releases", lang)
        for it in items: add_entry(fg, it)
        save_feed(fg, f"feed_91mobiles_ott_{lang}.xml")

    # ── Web series (last 7 days) ──
    for lang in M_LANGS:
        log.info("─ 91M Series %s", lang)
        try:
            items = _91m_section("web-series", lang, "Web Series", filter_days=7)
        except Exception as e:
            log.error("  Series %s ERROR: %s", lang, e, exc_info=True)
            items = []
        fg = new_feed(
            f"91Mobiles — {lang.title()} Web Series This Week",
            f"Web series in {lang} from the last 7 days on 91Mobiles",
            f"{MOBILES_BASE}/entertainment/web-series", lang)
        for it in items: add_entry(fg, it)
        save_feed(fg, f"feed_91mobiles_series_{lang}.xml")

def _91m_section(section, lang, category, filter_days=None):
    cutoff = datetime.now() - timedelta(days=filter_days) if filter_days else None

    # Try language-specific URL variants
    urls = [
        f"{MOBILES_BASE}/entertainment/{section}?language={lang}",
        f"{MOBILES_BASE}/entertainment/{section}/{lang}",
        f"{MOBILES_BASE}/entertainment/{section}",
    ]
    html, used_url = "", ""
    for u in urls:
        log.info("  trying %s", u)
        html = http_get(u)
        if html and len(html) > 3000:
            used_url = u
            break
        time.sleep(0.5)
    if not html:
        log.error("  ✗ could not load 91Mobiles %s", section)
        return []

    soup = BeautifulSoup(html, "lxml")
    raw, seen_urls = [], set()

    # ★ KEY FIX: find EVERY detail-page link on the listing page
    for a in soup.find_all("a", href=True):
        href = a["href"].split("?")[0]
        if not DETAIL_RE.search(href):
            continue
        full = urljoin(MOBILES_BASE, href)
        if full in seen_urls:
            continue
        seen_urls.add(full)

        # title from link text, title attr, or parent
        title = txt(a) or a.get("title","")
        if not title or len(title) < 2:
            parent = a.find_parent(["div","li","article","td"])
            if parent:
                h = parent.find(["h3","h2","h4","h5"])
                if h: title = txt(h)
                else:
                    for other_a in parent.find_all("a"):
                        t = txt(other_a)
                        if t and len(t) > 2:
                            title = t; break
        if not title or len(title) < 2:
            continue

        item = {"title": title, "link": full, "guid": full,
                "language": lang, "source": "91Mobiles", "category": category}

        # extract image, date, rating from parent container
        parent = a.find_parent(["div","li","article","td","tr"])
        if parent:
            img = parent.find("img")
            if img:
                src = (img.get("src") or img.get("data-src") or
                       img.get("data-lazy-src") or img.get("data-original"))
                if src: item["image"] = src
            dt = parent.find(class_=re.compile(r"date|time|release", re.I))
            if dt: item["release_date"] = txt(dt)
            rt = parent.find(class_=re.compile(r"rating|score|imdb", re.I))
            if rt: item["rating"] = txt(rt)
            # also try to get description from parent
            desc = parent.find("p")
            if desc: item["description"] = txt(desc)
        raw.append(item)

    # also check for JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, list): data = data[0] if data else {}
            if isinstance(data, dict) and data.get("name"):
                url = urljoin(MOBILES_BASE, data.get("url",""))
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    raw.append({
                        "title": data.get("name",""),
                        "link": url, "guid": url,
                        "language": lang, "source": "91Mobiles",
                        "category": category,
                        "image": data.get("image",""),
                        "description": data.get("description",""),
                    })
        except (json.JSONDecodeError, TypeError): pass

    log.info("  found %d raw items from listing", len(raw))

    # ── Enrich from detail pages (only if missing data) ──
    enriched = []
    for item in raw:
        needs_detail = (not item.get("description") or
                        not item.get("genre") or
                        not item.get("release_date"))
        if needs_detail and item.get("link"):
            detail = _91m_detail(item["link"], lang, category)
            if detail:
                for k in ["description","rating","genre","duration",
                          "release_date","image","language"]:
                    if not item.get(k) and detail.get(k):
                        item[k] = detail[k]
            time.sleep(DELAY)

        # language filter (lenient)
        item_lang = str(item.get("language","")).lower()
        if item_lang and item_lang != "n/a" and lang not in item_lang.replace(" ",""):
            # but allow if we haven't determined language yet
            if item_lang and len(item_lang) > 1:
                continue

        # date filter for web series
        if cutoff and item.get("release_date"):
            dt = parse_date(item["release_date"])
            if dt and dt < cutoff:
                continue

        enriched.append(item)

    # deduplicate by title
    seen, unique = set(), []
    for it in enriched:
        key = it.get("title","").lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(it)

    log.info("  → %d items for %s", len(unique), lang)
    return unique[:30]

def _91m_detail(url, lang, category):
    html = http_get(url)
    if not html: return None
    soup = BeautifulSoup(html, "lxml")
    item = {"language": lang, "source": "91Mobiles", "category": category}

    h1 = soup.find("h1")
    if h1: item["title"] = txt(h1)
    else:
        og = soup.find("meta", property="og:title")
        if og: item["title"] = og.get("content","").strip()

    og_img = soup.find("meta", property="og:image")
    if og_img: item["image"] = og_img.get("content","")
    else:
        img = soup.find("img", class_=re.compile(r"poster|banner|hero|main", re.I))
        if img: item["image"] = img.get("src","")

    og_desc = soup.find("meta", property="og:description")
    if og_desc: item["description"] = og_desc.get("content","").strip()
    else:
        meta = soup.find("meta", attrs={"name":"description"})
        if meta: item["description"] = meta.get("content","").strip()

    # parse metadata from li/dt-dd/div structures
    for el in soup.find_all(["li","dt","div","span"]):
        t = txt(el)
        if ":" in t and len(t) < 120:
            label, _, val = t.partition(":")
            ll, vv = label.strip().lower(), val.strip()
            if not vv or len(vv) > 80: continue
            if "rating" in ll or "imdb" in ll:    item["rating"] = vv
            elif "genre" in ll:                    item["genre"] = vv
            elif "duration" in ll or "runtime" in ll: item["duration"] = vv
            elif "release" in ll or "premiere" in ll or "stream" in ll:
                item["release_date"] = vv
            elif "language" in ll:                 item["language"] = vv

    # JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, list): data = data[0] if data else {}
            if isinstance(data, dict):
                for k in ["description","genre","duration","rating"]:
                    if not item.get(k):
                        v = data.get(k) or data.get(k.capitalize())
                        if v: item[k] = str(v)
                if not item.get("release_date"):
                    rd = data.get("datePublished") or data.get("releaseDate")
                    if rd: item["release_date"] = str(rd)
        except (json.JSONDecodeError, TypeError): pass

    return item

# ═══════════════════════════════════════════════════════════════════════════════
# 1TAMILMV
# ═══════════════════════════════════════════════════════════════════════════════

def scrape_tamilmv():
    log.info("=" * 60)
    log.info("1TamilMV")
    log.info("=" * 60)
    html, used_url = "", ""
    for url in TAMILMV_URLS:
        log.info("  trying %s", url)
        html = http_get(url)
        if html and len(html) > 2000:
            used_url = url; break
        time.sleep(1)
    if not html:
        log.error("  ✗ could not load 1TamilMV")
        save_empty("feed_1tamilmv.xml", "1TamilMV — Latest Releases",
                   "Latest releases from 1TamilMV", "https://www.1tamilmv.to/")
        return

    soup = BeautifulSoup(html, "lxml")
    items, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = txt(a)
        if "/topic/" in href and title and len(title) > 5:
            clean_url = href.split("&")[0].split("#")[0]
            if not clean_url.startswith("http"):
                clean_url = urljoin(used_url, clean_url)
            if clean_url in seen: continue
            seen.add(clean_url)
            item = {"title": title, "link": clean_url, "guid": clean_url,
                    "source": "1TamilMV", "category": "Release"}
            parent = a.find_parent(["li","tr","div","article"])
            if parent:
                tm = parent.find("time")
                if tm:
                    item["release_date"] = (tm.get("datetime") or
                                            tm.get("title") or txt(tm))
                else:
                    dt = parent.find(class_=re.compile(r"date|time", re.I))
                    if dt: item["release_date"] = (dt.get("title") or
                                                   dt.get("datetime") or txt(dt))
                desc = parent.find(class_=re.compile(r"desc|excerpt|snippet", re.I))
                if desc: item["description"] = txt(desc)
            items.append(item)

    seen_t, unique = set(), []
    for it in items:
        key = it["title"].lower().strip()
        if key not in seen_t:
            seen_t.add(key); unique.append(it)

    fg = new_feed("1TamilMV — Latest Releases",
                   "Latest movie & series releases from 1TamilMV", used_url)
    for it in unique[:30]: add_entry(fg, it)
    save_feed(fg, "feed_1tamilmv.xml")

# ═══════════════════════════════════════════════════════════════════════════════
# HOMEPAGE
# ═══════════════════════════════════════════════════════════════════════════════

def make_homepage():
    log.info("=" * 60)
    log.info("Homepage")
    log.info("=" * 60)
    feeds = sorted(f for f in os.listdir(BASE_DIR)
                   if f.startswith("feed_") and f.endswith(".xml"))
    g = {"toi":[], "ott":[], "series":[], "mv":[]}
    for f in feeds:
        n = f.replace("feed_","").replace(".xml","")
        if n.startswith("toi_movies_"):        g["toi"].append((f, n.replace("toi_movies_","").title()))
        elif n.startswith("91mobiles_ott_"):   g["ott"].append((f, n.replace("91mobiles_ott_","").title()))
        elif n.startswith("91mobiles_series_"):g["series"].append((f, n.replace("91mobiles_series_","").title()))
        elif "tamilmv" in n:                   g["mv"].append((f,"All"))

    def card(fn, lbl):
        return (f'<a href="{fn}" class="card"><div class="lang">{lbl}</div>'
                f'<div class="ico">📡</div><div class="fn">{fn}</div></a>')
    def section(title, sub, items):
        if not items: return ""
        return (f'<section><h2>{title}</h2><p class="sub">{sub}</p>'
                f'<div class="grid">{"".join(card(f,l) for f,l in items)}</div></section>')

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Entertainment RSS Feeds</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
background:#0f1117;color:#e0e0e0;line-height:1.6}}
.hd{{background:linear-gradient(135deg,#1a1d28,#2a2d3a);padding:3rem 1rem;
text-align:center;border-bottom:1px solid #2a2d3a}}
.hd h1{{font-size:2rem;color:#fff;margin-bottom:.3rem}}
.hd p{{color:#8b8d96}}.hd .ts{{color:#555;font-size:.8rem;margin-top:.5rem}}
.wrap{{max-width:1000px;margin:0 auto;padding:2rem 1rem}}
section{{margin-bottom:2.5rem}}
section h2{{font-size:1.3rem;color:#fff;border-bottom:2px solid #2a2d3a;
padding-bottom:.4rem;margin-bottom:.2rem}}
.sub{{color:#8b8d96;font-size:.85rem;margin-bottom:1rem}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:.8rem}}
.card{{display:block;background:#1a1d28;border:1px solid #2a2d3a;border-radius:8px;
padding:1rem;text-decoration:none;color:#e0e0e0;transition:.2s;text-align:center}}
.card:hover{{background:#222531;border-color:#3a3d4a;transform:translateY(-2px)}}
.lang{{font-size:1rem;font-weight:600;color:#6ea8fe;margin-bottom:.3rem}}
.ico{{font-size:1.3rem;margin-bottom:.3rem}}
.fn{{font-size:.7rem;color:#666;word-break:break-all}}
.ft{{text-align:center;padding:1.5rem;color:#444;font-size:.8rem;border-top:1px solid #2a2d3a}}
.ft a{{color:#6ea8fe;text-decoration:none}}
</style></head><body>
<div class="hd"><h1>🎬 Entertainment RSS Feeds</h1>
<p>Auto-updated feeds from Times of India, 91Mobiles &amp; 1TamilMV</p>
<p class="ts">Last updated: {now}</p></div>
<div class="wrap">
{section("Times of India — Movies","Movie reviews per language",g["toi"])}
{section("91Mobiles — OTT Releases","OTT releases this week per language",g["ott"])}
{section("91Mobiles — Web Series","Web series from last 7 days per language",g["series"])}
{section("1TamilMV — Latest","Latest releases from 1TamilMV",g["mv"])}
</div>
<div class="ft"><p>Feeds auto-update hourly via GitHub Actions</p>
<p><a href="https://www.rssboard.org/rss-specification">RSS 2.0</a></p></div>
</body></html>"""
    with open(os.path.join(BASE_DIR,"index.html"),"w",encoding="utf-8") as f:
        f.write(html)
    log.info("  ✓ index.html")

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    log.info("=" * 60)
    log.info("RSS Feed Generator — %s", datetime.now(timezone.utc).isoformat())
    log.info("=" * 60)
    scrape_toi()
    scrape_91mobiles()
    scrape_tamilmv()
    make_homepage()
    log.info("=" * 60)
    log.info("Done!")
    log.info("=" * 60)

if __name__ == "__main__":
    main()
