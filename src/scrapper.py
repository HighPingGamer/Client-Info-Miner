import json
import time
import random
import re
import os
import base64
from pathlib import Path
from urllib.parse import urlparse, urljoin, unquote
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ─────────────────────────────────────────
#  SETTINGS — only thing you ever change
# ─────────────────────────────────────────
MAX_PAGES       = 150
MAX_PDF_MB      = 50        # skip PDFs larger than this
TIMEOUT_MS      = 60000
AFTER_LOAD_MS   = 3000
DELAY_MIN       = 1.2
DELAY_MAX       = 3.0
SAVE_DIR        = Path(__file__).resolve().parents[1] / "Scraper Data"

PDF_KEYWORDS    = ("annual report", "financial statement", "sustainability report",
                   "esg report", "investor relations", "annual results",
                   "integrated report", "download", "report 20")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/122.0.0.0 Safari/537.36",
]

# ─────────────────────────────────────────
#  URL UTILITIES
# ─────────────────────────────────────────
def resolve_base(url):
    """Normalise input URL — try https://www first, then https:// without www."""
    if not url.startswith("http"):
        url = "https://" + url
    p    = urlparse(url)
    host = p.netloc or p.path.split("/")[0]
    # Strip trailing slash and path — start from root
    host = host.split("/")[0]
    # Always try www version as canonical
    if not host.startswith("www."):
        host = "www." + host
    return f"https://{host}"

def normalise(url):
    p = urlparse(url)
    path = p.path.rstrip("/") or "/"
    return f"{p.scheme}://{p.netloc}{path}"

def same_domain(url, domain):
    host = urlparse(url).netloc.lower().replace("www.","")
    base = domain.lower().replace("www.","")
    return host == base

# Matches /{region}/{lang}/ prefix e.g. /uae/en/, /ksa/ar/, /india/en-in/
_LOCALE_RE = re.compile(r'^/[a-z]{2,20}/[a-z]{2}(-[a-z]{2,4})?(?=/|$)', re.IGNORECASE)

def locale_normalise(url):
    """Strip region/language prefix from path for deduplication.
    /ksa/en/products and /uae/en/products both become /products."""
    p = urlparse(url)
    path = _LOCALE_RE.sub('', p.path) or '/'
    return f"{p.scheme}://{p.netloc}{path}"

def is_junk(url):
    bad = (".pdf",".jpg",".jpeg",".png",".gif",".zip",".docx",
           ".xlsx",".mp4",".mp3",".svg",".ico",".webp",".css",".js",".xml")
    low = url.lower()
    return (low.startswith(("mailto:","tel:","javascript:","#","data:")) or
            any(low.endswith(e) for e in bad))

def is_pdf_worth_downloading(url, anchor_text=""):
    """Return True if this link looks like a report worth downloading."""
    low_url    = url.lower()
    low_anchor = anchor_text.lower()
    # Anchor text is the strongest signal — trust it regardless of URL extension
    if any(kw in low_anchor for kw in PDF_KEYWORDS):
        return True
    # URL ends in .pdf — check URL patterns as fallback
    if low_url.endswith(".pdf"):
        url_signals = ("/annual", "/financial", "/sustainability", "/esg",
                       "/investor", "/report", "/download", "/publication")
        if any(sig in low_url for sig in url_signals):
            return True
    return False

# ─────────────────────────────────────────
#  EXTRACT FROM RENDERED PAGE
# ─────────────────────────────────────────
def get_page_text(page):
    try:
        return page.inner_text("body")
    except:
        return ""

def get_headings(page):
    headings = []
    try:
        for tag in ["h1","h2","h3"]:
            els = page.query_selector_all(tag)
            for el in els:
                t = el.inner_text().strip()
                if t and 2 < len(t) < 300:
                    headings.append(t)
    except:
        pass
    return headings

def get_meta(page, selectors):
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                v = el.get_attribute("content")
                if v and v.strip():
                    return v.strip()
        except:
            pass
    return ""

def get_links(page, domain):
    links = set()
    try:
        hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        for h in hrefs:
            if h and not is_junk(h) and same_domain(h, domain):
                links.add(normalise(h))
    except:
        pass
    return links

def get_pdf_candidates(page, domain):
    """Collect PDF/document links — catches <a href>, buttons, and JS-driven download links."""
    candidates = []
    seen = set()
    try:
        # Pass 1 — standard anchor tags (direct .pdf or doc URLs)
        pairs = page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => ({href: e.href, text: e.innerText.trim().slice(0,200)}))"
        )
        for pair in pairs:
            url  = pair.get("href", "")
            text = pair.get("text", "")
            if url and url not in seen and same_domain(url, domain) and is_pdf_worth_downloading(url, text):
                candidates.append({"url": url, "anchor": text})
                seen.add(url)
    except:
        pass

    try:
        # Pass 2 — any clickable element whose visible text signals a document download
        # Catches <button>, <div>, <span> with onclick or data-href used by JS-driven sites
        all_clickable = page.eval_on_selector_all(
            "a[href], [onclick], [data-href], [data-url]",
            """els => els.map(e => ({
                href: e.href || e.getAttribute('data-href') || e.getAttribute('data-url') || '',
                text: e.innerText.trim().slice(0,200)
            }))"""
        )
        for pair in all_clickable:
            url  = pair.get("href", "")
            text = pair.get("text", "")
            if url and url not in seen and is_pdf_worth_downloading(url, text):
                candidates.append({"url": url, "anchor": text})
                seen.add(url)
    except:
        pass

    return candidates

def get_socials(html):
    found = {}
    for p, label in [("linkedin","LinkedIn"),("twitter","Twitter"),
                     ("x.com","Twitter/X"),("facebook","Facebook"),
                     ("instagram","Instagram"),("youtube","YouTube")]:
        m = re.search(r'href=["\']([^"\']*'+p+r'[^"\']*)["\']', html, re.I)
        if m and label not in found:
            found[label] = m.group(1)
    return found

def get_emails(text):
    return list(set(re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)))

def get_phones(text):
    raw = re.findall(r"[\+]?[\d\s\(\)\-\.]{8,20}", text)
    out = []
    for p in raw:
        d = re.sub(r"\D","",p)
        if 7 <= len(d) <= 15:
            out.append(p.strip())
    return list(set(out))[:15]

def screenshot(page, path):
    try:
        page.screenshot(path=str(path), full_page=True, type="jpeg", quality=72)
        return True
    except:
        return False

def read_sitemap(page, base):
    urls = []
    for s in ["/sitemap.xml", "/sitemap_index.xml"]:
        try:
            page.goto(base+s, timeout=10000, wait_until="domcontentloaded")
            locs = re.findall(r"<loc>(.*?)</loc>", page.content())
            if locs:
                urls = [unquote(u.strip()) for u in locs]
                print(f"  ✅ Sitemap: {len(urls)} URLs found")
                return urls
        except:
            pass
    return urls

# ─────────────────────────────────────────
#  PDF DOWNLOADER
# ─────────────────────────────────────────
def download_pdfs(candidates, doc_dir):
    """Download collected PDF candidates. Returns list of document metadata dicts."""
    import urllib.request
    import urllib.error

    doc_dir.mkdir(parents=True, exist_ok=True)
    seen_urls = set()
    documents = []

    print(f"\n  📄 PDF Hunter — {len(candidates)} candidates found")

    for c in candidates:
        url = c["url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)

        raw_name = url.split("/")[-1].split("?")[0] or ""
        filename = re.sub(r"[^\w\-\.]", "_", raw_name)[:100] if raw_name else ""
        # If no usable filename, derive one from anchor text
        if not filename or filename in ("report.pdf", "report", ""):
            slug = re.sub(r"[^\w\s]", "", c["anchor"].lower().strip())[:50]
            slug = re.sub(r"\s+", "_", slug).strip("_") or "document"
            filename = slug + ".pdf"
        dest     = doc_dir / filename

        if dest.exists():
            print(f"     ✅ Already downloaded: {filename}")
            documents.append({"filename": filename, "url": url,
                               "anchor": c["anchor"], "status": "cached"})
            continue

        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENTS[0]})
            with urllib.request.urlopen(req, timeout=30) as resp:
                # Check size before downloading
                size_mb = int(resp.headers.get("Content-Length", 0)) / (1024*1024)
                if size_mb > MAX_PDF_MB:
                    print(f"     ⚠️  Skip (too large {size_mb:.0f}MB): {filename}")
                    continue
                content = resp.read()
                # Confirm it's actually a PDF by content-type or magic bytes
                content_type = resp.headers.get("Content-Type", "")
                is_pdf = ("pdf" in content_type.lower() or content[:4] == b"%PDF")
                if not is_pdf:
                    print(f"     ⚠️  Skip (not a PDF, type={content_type}): {filename}")
                    continue
                if len(content) / (1024*1024) > MAX_PDF_MB:
                    print(f"     ⚠️  Skip (too large after download): {filename}")
                    continue
                # Ensure filename ends in .pdf
                if not filename.lower().endswith(".pdf"):
                    filename = filename + ".pdf"
                    dest = doc_dir / filename
                dest.write_bytes(content)
                actual_mb = len(content) / (1024*1024)
                print(f"     ⬇️  Downloaded ({actual_mb:.1f}MB): {filename}")
                documents.append({"filename": filename, "url": url,
                                   "anchor": c["anchor"], "size_mb": round(actual_mb, 2),
                                   "status": "downloaded"})
        except Exception as e:
            print(f"     [!] Failed: {filename} — {e}")

    return documents

# ─────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────
def scrape(start_url):
    base   = resolve_base(start_url)
    domain = urlparse(base).netloc

    # Setup output folder
    folder  = SAVE_DIR / (domain.replace(".","_") + "_research")
    ss_dir  = folder / "screenshots"
    doc_dir = folder / "documents"
    ss_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*55}")
    print(f"  Researching : {base}")
    print(f"  Saving to   : {folder}")
    print(f"{'='*55}\n")

    data = {
        "domain":            domain,
        "base_url":          base,
        "page_title":        "",
        "meta_description":  "",
        "emails":            [],
        "phones":            [],
        "social_links":      {},
        "pages": [],          # list of {url, headings, text_snippet}
        "screenshot_paths":  [],
        "all_headings":      [],
        "raw_text":          "",
    }

    visited        = set()
    queue          = [base]
    queued         = {base}
    queued_norm    = {locale_normalise(base)}  # dedup by normalised path
    all_text       = ""
    pdf_candidates = []   # collected across all pages

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled",
                  "--no-sandbox","--disable-dev-shm-usage"]
        )
        ctx = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
                "DNT": "1",
            }
        )
        ctx.add_init_script("""
            Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
            Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3]});
            Object.defineProperty(navigator,'languages',{get:()=>['en-US','en','ar']});
            window.chrome={runtime:{}};
        """)

        pg = ctx.new_page()

        # Check sitemap — adds URLs to queue without assumptions
        sitemap_urls = read_sitemap(pg, base)
        for u in sitemap_urls:
            n    = normalise(u)
            norm = locale_normalise(n)
            if n not in queued and norm not in queued_norm and not is_junk(n) and same_domain(n, domain):
                queue.append(n)
                queued.add(n)
                queued_norm.add(norm)

        # ── Crawl ──────────────────────────
        while queue and len(visited) < MAX_PAGES:
            url = queue.pop(0)
            if url in visited:
                continue

            print(f"  → [{len(visited)+1}/{MAX_PAGES}] {url}")
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

            try:
                resp = pg.goto(url, timeout=TIMEOUT_MS, wait_until="domcontentloaded")

                if resp and resp.status not in (200, 304):
                    print(f"     [!] {resp.status} — skip")
                    continue

                # Wait for JS to render content — more reliable than networkidle
                try:
                    pg.wait_for_load_state("load", timeout=15000)
                except:
                    pass  # continue even if full load times out

                # Wait + scroll to trigger lazy content
                pg.wait_for_timeout(AFTER_LOAD_MS)
                pg.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                pg.wait_for_timeout(800)
                pg.evaluate("window.scrollTo(0, 0)")
                pg.wait_for_timeout(400)

                visited.add(url)

                # ── Screenshot every page ──
                ss_name = f"page_{len(visited):03d}.jpg"
                ss_path = ss_dir / ss_name
                if screenshot(pg, ss_path):
                    data["screenshot_paths"].append(str(ss_path))
                    print(f"     📸 Screenshot saved")

                # ── Grab data ──────────────
                if not data["page_title"]:
                    try: data["page_title"] = pg.title()
                    except: pass

                if not data["meta_description"]:
                    data["meta_description"] = get_meta(pg, [
                        'meta[name="description"]',
                        'meta[property="og:description"]',
                    ])

                page_text = get_page_text(pg)
                headings  = get_headings(pg)
                all_text += f"\n\n=== {url} ===\n{page_text}"

                data["pages"].append({
                    "url":          url,
                    "headings":     headings,
                    "text_snippet": page_text[:8000],  # increased from 3000
                })
                data["all_headings"].extend(headings)

                try:
                    html = pg.content()
                    data["social_links"].update(get_socials(html))
                except: pass

                # ── Find more links ─────────
                for lnk in get_links(pg, domain):
                    norm = locale_normalise(lnk)
                    if lnk not in queued and norm not in queued_norm:
                        queue.append(lnk)
                        queued.add(lnk)
                        queued_norm.add(norm)

                # ── Collect PDF candidates ──
                pdf_candidates.extend(get_pdf_candidates(pg, domain))

            except PlaywrightTimeout:
                print(f"     [!] Timeout — skip")
            except Exception as e:
                print(f"     [!] Error: {e}")

        browser.close()

    # ── Download PDFs ─────────────────────
    documents = download_pdfs(pdf_candidates, doc_dir)
    doc_json  = folder / "documents.json"
    with open(doc_json, "w", encoding="utf-8") as f:
        json.dump(documents, f, indent=2, ensure_ascii=False)
    print(f"  📄 Documents saved: {len(documents)} PDFs → {doc_json}")

    # ── Finalise ──────────────────────────
    data["emails"]       = get_emails(all_text)
    data["phones"]       = get_phones(all_text)
    data["all_headings"] = list(dict.fromkeys(data["all_headings"]))
    data["raw_text"]     = all_text[:80000]

    # Save JSON
    json_path = folder / f"{domain.replace('.','_')}_research.json"
    save = {k:v for k,v in data.items()}
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(save, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*55}")
    print(f"  ✅ Crawled   : {len(visited)} pages")
    print(f"  📸 Screenshots: {len(data['screenshot_paths'])}")
    print(f"  💾 Saved     : {json_path}")
    print(f"{'='*55}\n")

    return data, json_path

if __name__ == "__main__":
    url = input("Paste company URL:\n> ").strip()
    scrape(url)
    input("\nDone! Press Enter to close.")
