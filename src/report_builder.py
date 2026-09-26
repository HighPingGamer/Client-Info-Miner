import json
import os
import re
import time
import ctypes
from pathlib import Path
import fitz  # PyMuPDF
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.drawing.image import Image as XLImage
import ollama
import easyocr
import torch
import numpy as np
from PIL import Image as PILImage

# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────
TEXT_MODEL = "llama3.1"
SAVE_DIR   = Path(__file__).resolve().parents[1] / "Scraper Data"

# ─────────────────────────────────────────
#  SLEEP PREVENTION
# ─────────────────────────────────────────
def prevent_sleep():
    ES_CONTINUOUS       = 0x80000000
    ES_SYSTEM_REQUIRED  = 0x00000001
    ES_DISPLAY_REQUIRED = 0x00000002
    ctypes.windll.kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
    )
    print("  💡 Sleep prevention: ON")

def allow_sleep():
    ES_CONTINUOUS = 0x80000000
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    print("  💤 Sleep prevention: OFF")

# ─────────────────────────────────────────
#  LOGGER
# ─────────────────────────────────────────
LOG_FILE = None

def init_log(domain):
    global LOG_FILE
    log_path = SAVE_DIR / f"{domain.replace('.','_')}_AI_LOG.txt"
    LOG_FILE  = open(log_path, "w", encoding="utf-8")
    log(f"AI Processing Log — {domain}\n{'='*60}\n")
    print(f"  📋 Logging to: {log_path}")
    return log_path

def log(text):
    if LOG_FILE:
        LOG_FILE.write(text + "\n")
        LOG_FILE.flush()

def close_log():
    if LOG_FILE:
        LOG_FILE.close()

# ─────────────────────────────────────────
#  STYLES
# ─────────────────────────────────────────
DARK_BLUE   = "1F3864"
MID_BLUE    = "2E75B6"
LIGHT_BLUE  = "D6E4F0"
WHITE       = "FFFFFF"
GREY        = "F2F2F2"
YELLOW      = "FFF2CC"
YELLOW_DARK = "7D6608"
GREEN_LIGHT = "E2EFDA"
GREEN_DARK  = "375623"

def cell(ws, row, col, value, bg=WHITE, fg="1A1A1A", bold=False, size=11, indent=0):
    c = ws.cell(row=row, column=col, value=str(value) if value else "")
    c.font      = Font(bold=bold, color=fg, size=size, name="Calibri")
    c.fill      = PatternFill("solid", fgColor=bg)
    c.alignment = Alignment(horizontal="left", vertical="center",
                            wrap_text=True, indent=indent)
    c.border    = Border(bottom=Side(style="thin", color="DDDDDD"))
    return c

def banner(ws, row, text, ncols=5):
    ws.row_dimensions[row].height = 30
    c = ws.cell(row=row, column=1, value=text)
    c.font = Font(bold=True, color=WHITE, size=13, name="Calibri")
    c.fill = PatternFill("solid", fgColor=DARK_BLUE)
    c.alignment = Alignment(horizontal="left", vertical="center")
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncols)
    return row + 1

def section(ws, row, text, ncols=5):
    ws.row_dimensions[row].height = 20
    for col in range(1, ncols+1):
        c = ws.cell(row=row, column=col, value=text if col==1 else "")
        c.font = Font(bold=True, color=WHITE, size=11, name="Calibri")
        c.fill = PatternFill("solid", fgColor=MID_BLUE)
        c.alignment = Alignment(horizontal="left", vertical="center")
    return row + 1

def kv(ws, row, label, value, alt=False):
    bg = LIGHT_BLUE if alt else WHITE
    ws.row_dimensions[row].height = 18
    cell(ws, row, 1, label, bg=bg, bold=True)
    cell(ws, row, 2, value or "Not found", bg=bg)
    for col in [3,4,5]: cell(ws, row, col, "", bg=bg)
    return row + 1

def divider(ws, row, ncols=5):
    ws.row_dimensions[row].height = 5
    for col in range(1, ncols+1):
        ws.cell(row=row, column=col).fill = PatternFill("solid", fgColor=GREY)
    return row + 1

def list_rows(ws, start, items):
    row = start
    for i, item in enumerate(items or ["None found"]):
        bg = LIGHT_BLUE if i % 2 == 0 else WHITE
        ws.row_dimensions[row].height = 16
        cell(ws, row, 1, "", bg=bg)
        cell(ws, row, 2, item, bg=bg, indent=1)
        for col in [3,4,5]: cell(ws, row, col, "", bg=bg)
        row += 1
    return row

# ─────────────────────────────────────────
#  AI WRAPPERS
# ─────────────────────────────────────────
SYSTEM = """You are a data extraction engine.
STRICT OUTPUT RULES:
- Return ONLY the requested data, nothing else
- No markdown formatting — no **, no bullet points with *, no numbered lists
- No introductions, explanations, notes or commentary
- If nothing found, return exactly: NONE
- Never invent data not present in the input
- For lists: one plain item per line starting with -
- For people: Full Name | Job Title — one per line"""

def ask_llama(prompt, label="", num_predict=1200, num_ctx=32768):
    try:
        r = ollama.chat(
            model=TEXT_MODEL,
            options={"temperature": 0, "num_predict": num_predict, "num_ctx": num_ctx},
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user",   "content": prompt}
            ]
        )
        raw = r["message"]["content"].strip()
        raw = raw.replace("**", "").replace("__", "")
        # Strip leading chat filler
        for filler in ["here are","based on","note:","note that","i found",
                        "i can see","the following","below are","certainly",
                        "sure","please note","as requested"]:
            if raw.lower().startswith(filler):
                raw = raw[raw.index("\n")+1:].strip() if "\n" in raw else ""
        # Strip trailing chat filler lines
        TRAILING = ["let me know","feel free","hope this","i hope","please let me",
                    "is there anything","would you like","if you have any",
                    "don't hesitate","happy to help","anything else","note that"]
        lines = raw.split("\n")
        while lines and any(t in lines[-1].lower() for t in TRAILING):
            lines.pop()
        raw = "\n".join(lines).strip()
        log(f"\n[LLAMA] {label}")
        log(f"PROMPT (truncated):\n{prompt[:300]}...")
        log(f"RESPONSE:\n{raw}")
        log("-"*60)
        return raw
    except Exception as e:
        log(f"[LLAMA ERROR] {label}: {e}")
        print(f"     [!] Llama error: {e}")
        return ""

def unload_llama():
    try:
        ollama.chat(
            model=TEXT_MODEL,
            options={"num_predict": 1},
            keep_alive=0,
            messages=[{"role": "user", "content": "x"}]
        )
        print("  🔄 Llama unloaded from VRAM")
        time.sleep(3)
    except:
        pass

def ask_ocr(reader, path, page_url, label=""):
    try:
        img = PILImage.open(path).convert('RGB')
        result = reader.readtext(np.array(img), detail=1)
        lines = [text for _, text, conf in result if conf > 0.5]
        text = "\n".join(lines)
        log(f"\n[OCR] {label}\nURL: {page_url}\nRESPONSE:\n{text[:800]}\n" + "-"*60)
        return text
    except Exception as e:
        log(f"[OCR ERROR] {label}: {e}")
        print(f"     [!] OCR error: {e}")
        return ""

# ─────────────────────────────────────────
#  PARSERS
# ─────────────────────────────────────────
GROUP_WORDS = {
    "team","family","employees","staff","management","board","committee",
    "founders","partners","leadership","directors","executives","members",
    "group","division","department","unit","office","crew","workforce"
}

def parse_pipe(raw):
    out, seen = [], set()
    for line in raw.split("\n"):
        line = line.strip().lstrip("-•*1234567890.). ").strip()
        line = line.replace("**","")
        if "|" not in line: continue
        parts = line.split("|", 1)
        name  = parts[0].strip()
        title = parts[1].strip()
        if not name or len(name) < 5: continue
        if name.lower() in ("name","none","n/a","full name",""): continue
        if name.isupper() or "&" in name: continue
        # Must have at least two words (first + last name)
        if len(name.split()) < 2: continue
        # Reject if any word in name is a group word
        if any(w.lower() in GROUP_WORDS for w in name.split()): continue
        # Reject empty or placeholder titles
        if not title or title.lower() in ("none","n/a","unknown","no job title","no title",
                                           "no job title specified",""): continue
        key = name.lower()
        if key not in seen:
            seen.add(key)
            out.append((name, title))
    return out

FILLER_ANYWHERE = [
    "let me know","feel free","hope this","i hope","please let me",
    "is there anything","would you like","if you have any",
    "don't hesitate","happy to help","anything else","note that",
    "if you need","i can help","let me help","you're welcome",
    "glad to","of course","certainly","as requested"
]

def parse_list(raw):
    out, seen = [], set()
    skip = {"none","n/a","none found","none detected","not found","none visible"}
    junk_start = ["here ","note ","based ","the following","below","i ",
                  "please","*","#"]
    for line in raw.split("\n"):
        line = line.strip().lstrip("-•*0123456789.). ").strip()
        line = line.replace("**","").replace("__","")
        if not line or len(line) < 3: continue
        if line.lower() in skip: continue
        # Filter "Label: NONE" / "Label: $NONE" / "Label: N/A" entries
        if ":" in line:
            val = line.split(":", 1)[1].strip().lstrip("$£€").strip().lower()
            if val in ("none","n/a","","not found","not available","unknown"):
                continue
            if val.startswith(("none", "n/a", "not found", "not available", "unknown")):
                continue
        if any(line.lower().startswith(j) for j in junk_start): continue
        # Strip filler lines that appear anywhere in response
        if any(f in line.lower() for f in FILLER_ANYWHERE): continue
        if line.endswith(":"): continue
        if line.count("&") > 2: continue
        key = line.lower()
        if key not in seen:
            seen.add(key)
            out.append(line)
    return out

def dedupe_similar(items):
    """Remove near-duplicate entries — keeps the more descriptive version."""
    import re
    if not items:
        return items
    def normalize(s):
        # Keep parenthetical content (abbreviation expansions) for matching
        parens = re.findall(r'\(([^)]+)\)', s)
        s = re.sub(r'\s*\([^)]+\)', '', s)
        full = ' '.join([s] + parens)
        full = re.sub(r'[^a-z0-9\s]', '', full.lower())
        # Singular/plural: strip trailing s from words longer than 4 chars
        words = [w.rstrip('s') if len(w) > 4 else w for w in full.split()]
        return ' '.join(words)
    kept = []
    norms = [normalize(i) for i in items]
    for i, item in enumerate(items):
        dominated = False
        for j in range(len(items)):
            if i == j: continue
            wi = set(norms[i].split())
            wj = set(norms[j].split())
            # Character substring OR word-set subset (catches abbreviation vs full name)
            char_dup = norms[i] and norms[j] and (norms[i] in norms[j] or norms[j] in norms[i])
            word_dup = wi and wj and (wi.issubset(wj) or wj.issubset(wi))
            if char_dup or word_dup:
                if len(norms[i]) < len(norms[j]):
                    dominated = True
                    break
                elif norms[i] == norms[j] and i > j:
                    dominated = True
                    break
        if not dominated:
            kept.append(item)
    return kept

def extract_years(text):
    years = []
    for match in re.findall(r'\b(20[0-3][0-9])\b', text or ""):
        year = int(match)
        if 2000 <= year <= 2039:
            years.append(year)
    return years

def sort_recent_first(items):
    def key(pair):
        idx, item = pair
        years = extract_years(item)
        newest = max(years) if years else -1
        return (-newest if newest >= 0 else 9999, idx)
    return [item for _idx, item in sorted(enumerate(items or []), key=key)]

FINANCIAL_CORE_KEYWORDS = (
    "revenue", "turnover", "ebitda", "net profit", "operating profit",
    "gross profit", "total assets", "cash flow", "operating cash flow",
    "free cash flow", "cash", "debt", "net debt", "funding raised",
    "equity", "finance cost"
)
FINANCIAL_EXCLUDE_KEYWORDS = (
    "emission", "co2", "carbon", "energy", "power saving", "water",
    "diesel", "road distance", "nautical miles", "resource saving",
    "scope 1", "scope 2", "intensity", "tonnes", "tons", "sqm",
    "community investment", "raw material", "procurement", "travel"
)

def is_core_financial_item(item):
    text = (item or "").lower()
    if "currency not specified" in text:
        return False
    if "%" in text:
        return False
    if "ebitda" in text and "x" in text and "debt" not in text:
        return False
    if any(word in text for word in FINANCIAL_EXCLUDE_KEYWORDS):
        return False
    return any(word in text for word in FINANCIAL_CORE_KEYWORDS)

def filter_core_financials(items):
    return [item for item in (items or []) if is_core_financial_item(item)]

def metric_bucket(item):
    text = (item or "").lower()
    if "net debt" in text or re.search(r'\bdebt\b', text):
        return "Debt"
    if "ebitda" in text:
        return "EBITDA"
    if "net profit" in text or "net income" in text:
        return "Net Profit"
    if "operating profit" in text:
        return "Operating Profit"
    if "revenue" in text or "turnover" in text:
        return "Revenue"
    if "cash flow" in text:
        return "Cash Flow"
    if re.search(r'\bcash\b', text):
        return "Cash"
    if "total assets" in text or "asset" in text:
        return "Total Assets"
    if "equity" in text:
        return "Equity"
    if "funding" in text:
        return "Funding"
    return "Other"

def metric_value_text(item):
    if ":" in item:
        value = item.split(":", 1)[1]
    else:
        value = item
    value = value.split(" - Source:", 1)[0].strip()
    return value

def build_financial_trends(items):
    yearly = {}
    for item in filter_core_financials(items):
        years = extract_years(item)
        if not years:
            continue
        year = max(years)
        bucket = metric_bucket(item)
        yearly.setdefault(year, {})
        yearly[year].setdefault(bucket, [])
        value = metric_value_text(item)
        if value not in yearly[year][bucket]:
            yearly[year][bucket].append(value)

    if not yearly:
        return []

    rows = []
    years_desc = sorted(yearly.keys(), reverse=True)
    latest = years_desc[0]
    oldest = years_desc[-1]
    rows.append(f"Latest report year found: {latest}")
    if len(years_desc) > 1:
        rows.append(f"Year coverage found: {oldest}-{latest} ({len(years_desc)} years with core financial data)")
    else:
        rows.append("Year coverage found: only one year with core financial data")

    for year in years_desc:
        metrics = yearly[year]
        ordered = []
        for key in ("Revenue", "EBITDA", "Operating Profit", "Net Profit", "Cash Flow", "Cash", "Debt", "Total Assets", "Equity", "Funding"):
            if key in metrics:
                values = metrics[key]
                shown = " / ".join(values[:2])
                if len(values) > 2:
                    shown += f" / +{len(values)-2} more"
                ordered.append(f"{key}: {shown}")
        if ordered:
            rows.append(f"{year}: " + " | ".join(ordered))

    latest_metrics = yearly.get(latest, {})
    missing = [m for m in ("Revenue", "EBITDA", "Net Profit", "Cash Flow", "Cash", "Debt", "Total Assets") if m not in latest_metrics]
    if missing:
        rows.append("Missing from latest year: " + ", ".join(missing))

    if len(years_desc) >= 2:
        previous = years_desc[1]
        rows.append(f"Trend basis: compare latest year {latest} against previous available year {previous}; exact direction should be reviewed from the listed figures.")

    return rows

def clean_assets(items):
    """Remove N/A fields from asset strings — show name only if details unknown."""
    import re
    cleaned = []
    for item in items:
        item = re.sub(r'\s*\|\s*Capacity\s*:\s*N/?A', '', item, flags=re.IGNORECASE)
        item = re.sub(r'\s*\|\s*Location\s*:\s*N/?A', '', item, flags=re.IGNORECASE)
        item = re.sub(r'\s*\|\s*Size\s*:\s*N/?A', '', item, flags=re.IGNORECASE)
        item = item.strip(' |').strip()
        if item:
            cleaned.append(item)
    return cleaned

def parse_tags(raw):
    valid = {"people","services","assets","financials","company","contact","general"}
    tags  = []
    for part in raw.lower().replace("\n"," ").split(","):
        part = part.strip().strip("[]\"'")
        if part in valid:
            tags.append(part)
    return tags if tags else ["general"]

# ─────────────────────────────────────────
#  IMAGE COMPRESSION
# ─────────────────────────────────────────
def compress_image(path):
    try:
        from PIL import Image as PILImage
        import io
        with PILImage.open(path) as im:
            im = im.convert("RGB")
            ratio = min(1000/im.width, 1400/im.height, 1.0)
            if ratio < 1.0:
                im = im.resize((int(im.width*ratio), int(im.height*ratio)),
                               PILImage.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=60)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"     [!] Image error: {e}")
        return None

# ─────────────────────────────────────────
#  STEP 1 — TAGGING
# ─────────────────────────────────────────
# ─────────────────────────────────────────
#  STEP 1.5 — PDF DOCUMENT READER
# ─────────────────────────────────────────
FINANCIAL_KEYWORDS = ("revenue", "ebitda", "net profit", "gross profit", "total assets",
                      "earnings", "balance sheet", "income statement", "cash flow",
                      "operating profit", "net income", "turnover", "funding", "valuation")
ESG_KEYWORDS       = ("esg", "gri", "sasb", "cdp", "carbon", "co2", "emissions",
                      "sustainability", "renewable", "green", "net zero", "climate",
                      "environmental", "social", "governance")
ARABIC_RE          = re.compile(r'[\u0600-\u06FF]')

REPORT_SIGNALS = ("esg report", "sustainability report", "annual report", "investor",
                  "financial statement", "integrated report", "annual results",
                  "quarterly report", "interim report", "report.pdf")
SKIP_SIGNALS   = ("catalogue", "catalog", "download certificate", "download the certification",
                  "award letter", "download form", "download catalogue", "brochure")

PDF_CONTEXT_PAGES = 1
PDF_MAX_FIN_PAGES_PER_DOC = 24
PDF_MAX_ESG_PAGES_PER_DOC = 16
PDF_MAX_CHARS_PER_CHUNK = 4500
PDF_MAX_FIN_CHUNKS_TOTAL = 24
PDF_MAX_ESG_CHUNKS_TOTAL = 12

FINANCIAL_PRIORITY_TERMS = (
    "financial highlights", "statement of profit or loss", "income statement",
    "statement of financial position", "balance sheet", "statement of cash flows",
    "consolidated statement", "ebitda", "operating profit", "net profit",
)

def is_report_document(doc):
    anchor = doc.get("anchor", "").lower()
    fname  = doc.get("filename", "").lower()
    haystack = f"{anchor} {fname}"
    if any(s in haystack for s in SKIP_SIGNALS):
        return False
    if any(s in haystack for s in REPORT_SIGNALS):
        return True
    return any(s in fname for s in ("esg", "sustainability", "annual", "investor", "financial", "report"))

def select_scored_pages(scored_pages, limit):
    top = sorted(scored_pages, key=lambda item: (-item[1], item[0]))[:limit]
    return sorted(pn for pn, _score in top)

def make_pdf_chunks(page_nums, page_texts, max_chunks, kind):
    chunks = []
    pages_with_context = set()
    for pn in page_nums:
        for p in range(pn - PDF_CONTEXT_PAGES, pn + PDF_CONTEXT_PAGES + 1):
            if 0 <= p < len(page_texts):
                pages_with_context.add(p)

    page_runs = []
    for p in sorted(pages_with_context):
        if not page_runs or p != page_runs[-1][-1] + 1:
            page_runs.append([p])
        else:
            page_runs[-1].append(p)

    for page_run in page_runs:
        current = []
        current_len = 0
        start_page = None
        end_page = None
        for p in page_run:
            page_text = (page_texts[p] or "").strip()
            if not page_text:
                continue
            labelled = f"\n--- Page {p+1} ---\n{page_text}\n"
            if current and current_len + len(labelled) > PDF_MAX_CHARS_PER_CHUNK:
                chunks.append({
                    "kind": kind,
                    "page_start": start_page,
                    "page_end": end_page,
                    "text": "".join(current)[:PDF_MAX_CHARS_PER_CHUNK],
                })
                current = []
                current_len = 0
                start_page = None
                end_page = None
                if len(chunks) >= max_chunks:
                    return chunks
            if start_page is None:
                start_page = p + 1
            end_page = p + 1
            current.append(labelled)
            current_len += len(labelled)

        if current:
            chunks.append({
                "kind": kind,
                "page_start": start_page,
                "page_end": end_page,
                "text": "".join(current)[:PDF_MAX_CHARS_PER_CHUNK],
            })
            if len(chunks) >= max_chunks:
                return chunks
    return chunks

def chunk_source_label(filename, chunk):
    start = chunk.get("page_start")
    end = chunk.get("page_end")
    if start and end and start != end:
        return f"{filename} pages {start}-{end}"
    if start:
        return f"{filename} page {start}"
    return filename

def read_documents(research_folder):
    """
    Step 1.5 — Read downloaded PDFs using PyMuPDF.
    Two-pass: scan report-like PDFs cheaply, then keep bounded page chunks.
    Returns metadata plus financial/esg chunks that stay small enough for local LLMs.
    """
    doc_json = Path(research_folder) / "documents.json"
    doc_dir  = Path(research_folder) / "documents"

    if not doc_json.exists():
        print("\n  📄 Step 1.5 — No documents.json found, skipping PDF reading")
        return []

    with open(doc_json, encoding="utf-8") as f:
        documents = json.load(f)

    if not documents:
        print("\n  📄 Step 1.5 — No PDFs downloaded, skipping")
        return []

    print(f"\n  📄 Step 1.5 — PDF Reader ({len(documents)} documents)")
    results = []

    for doc in documents:
        if not is_report_document(doc):
            continue

        pdf_path = doc_dir / doc["filename"]
        if not pdf_path.exists():
            continue

        pdf = None
        try:
            pdf = fitz.open(str(pdf_path))

            sample_text = ""
            for i in range(min(3, len(pdf))):
                sample_text += pdf[i].get_text()
            arabic_chars = len(ARABIC_RE.findall(sample_text))
            total_chars  = max(len(sample_text), 1)
            if arabic_chars / total_chars > 0.4:
                print(f"     ⏭️  Skip (Arabic): {doc['filename']}")
                continue

            print(f"     📖 Reading: {doc['filename']} ({len(pdf)} pages)")

            financial_scored = []
            esg_scored       = []
            page_texts       = []

            for page_num in range(len(pdf)):
                raw_text = pdf[page_num].get_text()
                page_texts.append(raw_text)
                page_lower = raw_text.lower()
                if not page_lower.strip():
                    continue

                fin_hits = sum(1 for kw in FINANCIAL_KEYWORDS if kw in page_lower)
                esg_hits = sum(1 for kw in ESG_KEYWORDS if kw in page_lower)
                fin_hits += sum(2 for term in FINANCIAL_PRIORITY_TERMS if term in page_lower)

                if fin_hits >= 1:
                    financial_scored.append((page_num, fin_hits))
                if esg_hits >= 1:
                    esg_scored.append((page_num, esg_hits))

            financial_pages = select_scored_pages(financial_scored, PDF_MAX_FIN_PAGES_PER_DOC)
            esg_pages = select_scored_pages(esg_scored, PDF_MAX_ESG_PAGES_PER_DOC)

            financial_chunks = make_pdf_chunks(financial_pages, page_texts, 10, "financial")
            esg_chunks = make_pdf_chunks(esg_pages, page_texts, 6, "esg")

            fin_text = "\n".join(c["text"] for c in financial_chunks)[:12000]
            esg_text = "\n".join(c["text"] for c in esg_chunks)[:8000]

            print(f"        Financial pages kept: {len(financial_pages)} | ESG pages kept: {len(esg_pages)}")

            results.append({
                "filename":          doc["filename"],
                "url":               doc.get("url", ""),
                "anchor":            doc.get("anchor", ""),
                "is_report":         True,
                "financial_text":    fin_text,
                "esg_text":          esg_text,
                "financial_chunks":  financial_chunks,
                "esg_chunks":        esg_chunks,
                "fin_page_count":    len(financial_pages),
                "esg_page_count":    len(esg_pages),
            })
        except Exception as e:
            print(f"     [!] PDF read failed for {doc['filename']}: {e}")
        finally:
            if pdf is not None:
                pdf.close()

    if not results:
        print("     No report-like PDFs found for document extraction")
    return results


def extract_from_documents(doc_results, domain):
    """
    Llama reads bounded PDF chunks and extracts structured financial + ESG data.
    Returns dict with financials, financial_health, esg, sustainability keys.
    """
    if not doc_results:
        return {"financials": [], "financial_trends": [], "financial_health": [], "esg": [], "sustainability": []}

    print("\n  📊 Step 4.5 — Document extraction (PDF-based)...")

    report_docs = [d for d in doc_results if d.get("is_report")]
    skipped     = len(doc_results) - len(report_docs)
    print(f"     Using {len(report_docs)}/{len(doc_results)} PDFs as reports ({skipped} skipped)")

    financial_tasks = []
    esg_tasks = []
    for d in report_docs:
        for chunk in d.get("financial_chunks", []):
            financial_tasks.append((d["filename"], chunk))
        for chunk in d.get("esg_chunks", []):
            esg_tasks.append((d["filename"], chunk))

    financial_tasks = financial_tasks[:PDF_MAX_FIN_CHUNKS_TOTAL]
    esg_tasks = esg_tasks[:PDF_MAX_ESG_CHUNKS_TOTAL]

    doc_financials   = []
    doc_health       = []
    doc_esg          = []
    doc_sustainability = []

    for idx, (filename, chunk) in enumerate(financial_tasks, 1):
        label = chunk_source_label(filename, chunk)
        print(f"     → Financial chunk {idx}/{len(financial_tasks)}: {label}")
        raw = ask_llama(
            f"Company: {domain}\nSource: {label}\n\n{chunk['text']}\n\n"
            f"Extract key financial figures from this report excerpt.\n"
            f"FORMAT each line as: [Metric]: [Value] [Currency] ([Year]) - Source: {label}\n"
            f"INCLUDE: Revenue, EBITDA, Net Profit, Total Assets, Operating Profit, Cash Flow, Debt, Cash, Funding raised\n"
            f"EXCLUDE: capacity (MW/kWh), headcount, percentages without a base figure\n"
            f"USE ONLY figures explicitly stated - no calculations or estimates\n"
            f"One per line starting with -\n"
            f"If none found: NONE",
            label=f"doc_financials_{idx}",
            num_predict=700,
            num_ctx=8192,
        )
        doc_financials.extend(parse_list(raw))

    doc_financials = sort_recent_first(filter_core_financials(dedupe_similar(doc_financials)))
    doc_trends = build_financial_trends(doc_financials)

    if doc_financials:
        raw_health = ask_llama(
            f"Company: {domain}\n\nExtracted financial evidence:\n"
            f"{chr(10).join('- ' + x for x in doc_financials[:40])}\n\n"
            f"Write a financial health assessment using only the extracted evidence.\n"
            f"Focus on revenue, EBITDA or operating profit, net profit, cash flow, cash, debt, assets, and year-over-year direction when present.\n"
            f"Do not invent missing figures. If evidence is missing, say what is missing.\n"
            f"FORMAT as bullets starting with - . Keep it short and practical.",
            label="doc_financial_health",
            num_predict=900,
            num_ctx=8192,
        )
        doc_health = parse_list(raw_health)

    for idx, (filename, chunk) in enumerate(esg_tasks, 1):
        label = chunk_source_label(filename, chunk)
        print(f"     → ESG chunk {idx}/{len(esg_tasks)}: {label}")
        raw_esg = ask_llama(
            f"Company: {domain}\nSource: {label}\n\n{chunk['text']}\n\n"
            f"Extract ESG ratings, certifications and sustainability metrics.\n"
            f"FORMAT: [Metric/Rating]: [Value or Score] - Source: {label}\n"
            f"INCLUDE: ESG framework used (GRI/SASB/CDP), ratings, scores, certifications\n"
            f"One per line starting with -\n"
            f"If none: NONE",
            label=f"doc_esg_{idx}",
            num_predict=500,
            num_ctx=8192,
        )
        raw_sust = ask_llama(
            f"Company: {domain}\nSource: {label}\n\n{chunk['text']}\n\n"
            f"Extract green energy and sustainability performance metrics.\n"
            f"FORMAT: [Metric]: [Value with unit] ([Year]) - Source: {label}\n"
            f"INCLUDE: CO2 avoided/reduced, renewable capacity, energy generated, net zero targets, PPA volumes\n"
            f"One per line starting with -\n"
            f"If none: NONE",
            label=f"doc_sustainability_{idx}",
            num_predict=500,
            num_ctx=8192,
        )
        doc_esg.extend(parse_list(raw_esg))
        doc_sustainability.extend(parse_list(raw_sust))

    return {
        "financials":       sort_recent_first(dedupe_similar(doc_financials)),
        "financial_trends": doc_trends,
        "financial_health": dedupe_similar(doc_health),
        "esg":              dedupe_similar(doc_esg),
        "sustainability":   dedupe_similar(doc_sustainability),
    }


def tag_pages(data, narrations):
    print("\n  🏷️  Step 1 — Tagging all pages...")
    pages  = data.get("pages", [])
    tagged = []

    # Build OCR lookup by index for fast access
    ocr_by_idx = {n["page_num"] - 1: n["narration"] for n in narrations}

    for i, page in enumerate(pages):
        url  = page.get("url", "")
        text = page.get("text_snippet", "")[:1000]
        hdgs = " | ".join(page.get("headings", [])[:5])
        ocr  = ocr_by_idx.get(i, "")[:500]

        print(f"     → [{i+1}/{len(pages)}] {url}")

        raw = ask_llama(
            f"URL: {url}\n"
            f"Headings: {hdgs}\n"
            f"Text preview:\n{text}\n"
            + (f"Screenshot text:\n{ocr}\n\n" if ocr else "\n")
            + f"Assign ALL relevant tags to this page from this list:\n"
            f"people, services, assets, financials, company, contact, general\n\n"
            f"Rules:\n"
            f"- A page CAN have multiple tags\n"
            f"- people = team pages, leadership pages, board pages ONLY — NOT project pages, testimonial pages, press releases, blog posts, or partner announcements\n"
            f"- services = category or range pages describing a group of products/services the company sells — NOT individual product SKU pages, project case studies, testimonials, or pages that merely mention a service in passing\n"
            f"- assets = projects, installations, owned facilities, PPAs\n"
            f"- financials = revenue, profit, funding, investment, valuation, financial figures in USD/SAR/AED\n"
            f"- company = about, mission, history, overview\n"
            f"- contact = addresses, phones, emails, offices\n"
            f"- general = anything else\n\n"
            f"Return ONLY the tags as comma separated values. Nothing else.\n"
            f"Example: people, services",
            label=f"tag_{i+1}",
            num_predict=50,
            num_ctx=4096
        )

        tags = parse_tags(raw)
        tagged.append({**page, "tags": tags})
        print(f"        Tags: {tags}")

    print(f"\n  ✅ Tagged {len(tagged)} pages")
    return tagged

# ─────────────────────────────────────────
#  STEP 2 — TEXT EXTRACTION
# ─────────────────────────────────────────
def build_tagged_context(tagged_pages, target_tag, narrations=None):
    ctx      = ""
    count    = 0
    ocr_map  = {n["url"]: n["narration"] for n in narrations} if narrations else {}
    for p in tagged_pages:
        if target_tag in p.get("tags", []):
            ctx  += f"=== PAGE: {p['url']} ===\n"
            hdgs  = " | ".join(p.get("headings", [])[:8])
            if hdgs:
                ctx += f"Headings: {hdgs}\n"
            ctx  += p.get("text_snippet", "") + "\n"
            # Append OCR if scraped text is thin (team/profile pages)
            ocr = ocr_map.get(p["url"], "")
            if ocr and len(p.get("text_snippet","")) < 500:
                ctx += f"[OCR]\n{ocr}\n"
            ctx  += "\n"
            count += 1
    print(f"     [Context] '{target_tag}' → {count} pages")
    return ctx

# Known outsiders per domain — names that appear on the site but don't work there
KNOWN_OUTSIDERS = {
    "www.yellowdoorenergy.com": {
        "neville d'souza", "matthias riehle", "leya al damani", "sonali dhawan",
        "khalid rashid al zayani", "hisham al amoudi", "lucy heintz",
        "majid al futtaim", "rory mccarthy", "paavan bhargava"
    },
    "www.suhailbahwangroup.com": {
        "mohammed al barwani", "fathi al balushi", "dr. josé alexandre cunha",
        "jose alexandre cunha", "ilham murtadha al hamaid", "dr. sultan al busaidi",
        "sultan al busaidi", "sheikh saud bahwan",
        "sultan haitham bin tariq al said", "haitham bin tariq al said",
        "sayyid fahad al julanda al said", "fahad al julanda al said"
    }
}

def is_outsider(name, title, domain):
    """Return True if this person is a known outsider for this domain,
    or if their title explicitly names a different company."""
    import re
    # Strip honorifics before matching
    honorifics = r'^(mr\.?|ms\.?|mrs\.?|dr\.?|prof\.?|h\.e\.?|his\s+excellency|his\s+highness|her\s+highness|hh\s+|h\.h\.?|sheikha?\s+|sayyid\s+|his\s+majesty|sultan\s+)\s*'
    name_clean = re.sub(honorifics, '', name.lower().strip(), flags=re.IGNORECASE).strip()
    name_lower = name.lower().strip()
    # Check known outsiders list (both with and without honorifics)
    outsiders = KNOWN_OUTSIDERS.get(domain, set())
    if name_lower in outsiders or name_clean in outsiders:
        return True
    # Check if title names another company (various separator formats)
    other_company_patterns = [
        r'\bof\s+(?!Yellow Door|{d})\w[\w\s]+(?:Group|Company|Corp|Inc|Ltd|LLC|GmbH|Holdings|Investments|Hospital|Bank|Fund)\b',
        r',\s*(?!Yellow Door|{d})\w[\w\s]+(?:Group|Company|Corp|Inc|Ltd|LLC|GmbH|Holdings|Investments|Hospital|Bank|Fund)\b',
        r'\bfor\s+(?!Yellow Door|{d})\w[\w\s]+(?:Group|Company|Corp|Inc|Ltd|LLC|GmbH|Holdings|Investments|Hospital|Bank|Fund)\b',
        r'\bat\s+(?!Yellow Door|{d})\w[\w\s]+(?:Group|Company|Corp|Inc|Ltd|LLC|GmbH|Holdings|Investments|Hospital|Bank|Fund)\b',
    ]
    brand = domain.replace("www.", "").replace(".com", "").replace("-", " ")
    for pat in other_company_patterns:
        if re.search(pat.replace("{d}", brand), title, re.IGNORECASE):
            return True
    return False

def select_people_pages(pages):
    """Select official leadership/board/profile pages without relying only on AI tags."""
    selected = []
    for p in pages or []:
        url = p.get("url", "").lower()
        if any(x in url for x in ("/media/", "/news/", "/events/", "/press-release/", "/insights/", "/blog/", "/articles/")):
            continue
        headings = " ".join(p.get("headings", [])).lower()
        text = p.get("text_snippet", "").lower()
        official = any(x in url for x in (
            "/board-of-directors", "/executive-management", "/leadership",
            "/corporate-profile/", "/team", "/management",
        ))
        report_leadership = (
            "/reports/" in url
            and any(x in headings + " " + text for x in (
                "leadership", "chairman", "chief executive officer", "ceo message"
            ))
        )
        if official or report_leadership:
            selected.append(p)
    return selected

def extract_currency_lines(text, source):
    """Extract explicit metric/value pairs, including SAR-in-BN report layouts."""
    results = []
    financial = re.compile(
        r"(revenue|net income|net profit|operating profit|ebitda|assets|liabilit|cash flow|earnings|turnover)",
        re.I,
    )
    metric_line = re.compile(
        r"(?P<label>revenue|net income|net profit|operating profit|ebitda|assets|liabilit(?:ies|y)|cash flow|earnings|turnover)"
        r"[^\d$€£]*(?P<value>[$€£]?\s*[\d,.]+(?:\s*(?:bn|billion|m|million|thousand))?)",
        re.I,
    )
    unit_context = re.search(r"(SAR|USD|AED|OMR|BHD|KWD|QAR)\s+IN\s+(BN|BILLION|M|MILLION)", text or "", re.I)
    unit = unit_context.group(0) if unit_context else ""
    seen = set()
    for raw in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw).strip(" -•")
        if not financial.search(line):
            continue
        m = metric_line.search(line)
        if not m:
            continue
        value = m.group("value").strip()
        if unit and not re.search(r"(?:SAR|USD|AED|OMR|BHD|KWD|QAR)", value, re.I):
            value = f"{value} {unit}"
        item = f"{m.group('label').title()}: {value} - Source: {source}"
        key = item.lower()
        if key not in seen:
            seen.add(key)
            results.append(item)
    return results

def extract_employee_lines(pages):
    """Extract explicit workforce/headcount facts without treating them as people."""
    out = []
    seen = set()
    pattern = re.compile(
        r"(?:more than |over |approximately |about |around )?[\d,]+\+?\s+(?:employees|workforce|talented individuals)",
        re.I,
    )
    for p in pages or []:
        text = " ".join(p.get("headings", [])) + "\n" + p.get("text_snippet", "")
        for m in pattern.finditer(text):
            sentence = re.search(r"[^.]{0,100}" + re.escape(m.group(0)) + r"[^.]{0,140}", text, re.I)
            value = re.sub(r"\s+", " ", sentence.group(0) if sentence else m.group(0)).strip()
            item = f"{value} - Source: {p.get('url', '')}"
            key = item.lower()
            if key not in seen:
                seen.add(key)
                out.append(item)
    return out

def text_extraction(data, tagged_pages, narrations=None):
    print("\n  📝 Step 2 — Text extraction (Llama)...")
    domain   = data.get("domain", "this company")
    full_ctx = ""
    for p in tagged_pages:
        full_ctx += f"=== PAGE: {p['url']} ===\n"
        full_ctx += p.get("text_snippet","") + "\n\n"
    full_ctx = full_ctx[:80000]  # ~20K tokens — stays within num_ctx=32768

    print("     → Description...")
    description = ask_llama(
        f"{full_ctx}\n\n"
        f"In 4 sentences what does {domain} do? "
        f"Facts only from the text above. No commentary.",
        label="description"
    )

    print("     → Industry...")
    industry = ask_llama(
        f"{full_ctx}\n\nWhat industry and sector? One sentence.",
        label="industry"
    )

    # Per-page people extraction — each page gets full context and individual attention
    ocr_map      = {n["url"]: n["narration"] for n in narrations} if narrations else {}
    # Hard exclude news/media/event/blog URLs from people extraction — these contain external names
    NEWS_URL_PATTERNS = ("/media/", "/news/", "/events/", "/press-release/", "/insights/", "/blog/", "/articles/")
    people_pages = [
        p for p in select_people_pages(tagged_pages)
        if not any(pat in p.get("url", "") for pat in NEWS_URL_PATTERNS)
    ]
    print(f"     → People... ({len(people_pages)} pages, per-page mode)")
    people_pairs = []
    seen_names   = set()
    for p in people_pages:
        ctx  = f"=== PAGE: {p['url']} ===\n"
        hdgs = " | ".join(p.get("headings", [])[:8])
        if hdgs:
            ctx += f"Headings: {hdgs}\n"
        ctx += p.get("text_snippet", "") + "\n"
        ocr  = ocr_map.get(p["url"], "")
        if ocr and len(p.get("text_snippet","")) < 500:
            ctx += f"[OCR]\n{ocr}\n"
        raw = ask_llama(
            f"Company: {domain}\n\n{ctx}\n\n"
            f"Read the page above carefully.\n\n"
            f"Your ONE job: identify people who would appear on {domain}'s official Team or About Us page.\n\n"
            f"Ask yourself for each named person:\n"
            f"  - Do they hold a job AT {domain}?\n"
            f"  - Or are they mentioned as a customer, partner, government official, event attendee, journalist, or someone from another organisation?\n\n"
            f"ONLY include people who genuinely work at or lead {domain}.\n"
            f"Format: Full Name | Job Title\n"
            f"- First and last name required\n"
            f"- Job title must be their role AT {domain}, not at another company\n"
            f"- CRITICAL: DO NOT use your training data. Only use what is written above.\n"
            f"- If none qualify: NONE",
            label=f"people_{p['url'].rstrip('/').split('/')[-1]}",
            num_predict=500
        )
        for name, title in parse_pipe(raw):
            # Drop page-heading non-titles
            if title.lower().strip() in ("chairman's message", "vice chairperson's message",
                                          "ceo's message", "founder's message", "message", ""):
                continue
            name_l = name.lower().strip()
            # Deduplicate — skip if any word in this name already seen as a full name token
            name_words = set(name_l.split())
            already_seen = any(
                name_words.issubset(set(existing.split())) or
                set(existing.split()).issubset(name_words)
                for existing in seen_names
            )
            if not already_seen and not is_outsider(name, title, domain):
                # Prefer the longer/more complete name
                for existing in list(seen_names):
                    existing_words = set(existing.split())
                    if name_words.issubset(existing_words) or existing_words.issubset(name_words):
                        if len(name_l) > len(existing):
                            seen_names.discard(existing)
                            people_pairs = [(n, t) for n, t in people_pairs if n.lower() != existing]
                        break
                seen_names.add(name_l)
                people_pairs.append((name, title))
    people_raw = "\n".join(f"{n} | {t}" for n, t in people_pairs)

    SERVICES_NOISE_PATTERNS = ("/projects/", "/insights/", "/blog/", "/careers/", "/teams/", "/press-release/", "/media/", "/news/", "/events/", "/testimonials")
    PRIMARY_SERVICE_PATTERNS = ("/solutions/", "/services/", "/products/")

    def url_depth(url):
        from urllib.parse import urlparse
        return len([s for s in urlparse(url).path.split("/") if s])

    services_pages = [
        p for p in tagged_pages
        if "services" in p.get("tags", [])
        and not any(pat in p.get("url", "") for pat in SERVICES_NOISE_PATTERNS)
        and url_depth(p.get("url", "")) <= 3   # skip deep SKU/product-detail URLs
    ]
    # Cap at 20 pages — enough to capture all product categories, not individual SKUs
    services_pages = services_pages[:20]
    # Build context with confidence markers
    services_ctx = ""
    for p in services_pages:
        is_primary = any(pat in p.get("url", "") for pat in PRIMARY_SERVICE_PATTERNS)
        marker = "[PRIMARY SOURCE — high confidence]" if is_primary else "[SECONDARY SOURCE — low confidence]"
        services_ctx += f"=== PAGE: {p['url']} {marker} ===\n"
        hdgs = " | ".join(p.get("headings", [])[:8])
        if hdgs:
            services_ctx += f"Headings: {hdgs}\n"
        services_ctx += p.get("text_snippet", "") + "\n\n"
    print(f"     [Context] 'services' → {len(services_pages)} pages ({sum(1 for p in services_pages if any(pat in p.get('url','') for pat in PRIMARY_SERVICE_PATTERNS))} primary)")
    print("     → Services...")
    services_raw = ask_llama(
        f"Company: {domain}\n\n{services_ctx}\n\n"
        f"For each item you consider listing, ask yourself:\n"
        f"'Is this a specific named service or product {domain} sells to paying customers, "
        f"described in enough detail that a customer could buy it — "
        f"or is it a label, heading, navigation item, category name, or vague phrase?'\n\n"
        f"Only include items where the answer is clearly YES to the first part.\n"
        f"Prefer items from [PRIMARY SOURCE] pages over [SECONDARY SOURCE] pages.\n"
        f"One per line starting with -\n"
        f"USE ONLY text provided — no outside knowledge\n"
        f"If none qualify: NONE",
        label="services"
    )

    assets_ctx = build_tagged_context(tagged_pages, "assets")
    print("     → Assets...")
    assets_raw = ask_llama(
        f"Company: {domain}\n\n{assets_ctx}\n\n"
        f"For each item you consider listing, ask yourself:\n"
        f"'Is this a distinct physical asset, installation or facility that {domain} owns or operates, "
        f"with a specific name and location — or is it a client name, a product, a partnership, or a vague reference?'\n\n"
        f"Only include items where the answer is clearly YES.\n"
        f"FORMAT: Asset Name, Location, Capacity/Size — only include fields explicitly stated, omit the rest\n"
        f"One per line starting with -\n"
        f"USE ONLY text provided — no outside knowledge\n"
        f"If none qualify: NONE",
        label="assets"
    )

    financial_pages = [p for p in tagged_pages if (
        "financials" in p.get("tags", []) or
        any(x in p.get("url", "").lower() for x in (
            "/investors", "/reports/", "/financial", "/earnings")) or
        any(x in " ".join(p.get("headings", [])).lower() for x in (
            "revenue", "net income", "assets (sar", "financial highlights")))]
    financials_ctx = ""
    deterministic_financials = []
    for p in financial_pages:
        source = p.get("url", "")
        page_text = " | ".join(p.get("headings", [])[:20]) + "\n" + p.get("text_snippet", "")
        financials_ctx += f"=== PAGE: {source} ===\n{page_text}\n\n"
        deterministic_financials.extend(extract_currency_lines(page_text, source))
    financials_ctx = financials_ctx[:100000]
    print(f"     [Context] 'financials' → {len(financial_pages)} pages")
    print("     → Financials...")
    finance_raw = ask_llama(
        f"Company: {domain}\n\n{financials_ctx}\n\n"
        f"For each monetary figure you consider listing, ask yourself:\n"
        f"'Would this figure appear in the Financial Highlights section of {domain}'s "
        f"annual report or investor presentation — as a company-level result?'\n\n"
        f"Only include figures where the answer is clearly YES.\n"
        f"FORMAT: [What it is]: [Exact amount with currency]\n"
        f"One per line starting with -\n"
        f"USE ONLY figures explicitly stated in the text — no estimates, no outside knowledge\n"
        f"If none qualify: NONE",
        label="financials"
    )

    print("     → Highlights...")
    highlights_raw = ask_llama(
        f"{full_ctx}\n\nList key facts, awards, certifications.\n"
        f"One per line starting with -\n"
        f"Short and factual only.",
        label="highlights"
    )

    financials = parse_list(finance_raw)
    for item in deterministic_financials:
        if item.lower() not in {x.lower() for x in financials}:
            financials.append(item)

    highlights = parse_list(highlights_raw)
    for item in extract_employee_lines(tagged_pages):
        if item.lower() not in {x.lower() for x in highlights}:
            highlights.append(item)

    return {
        "description": description,
        "industry":    industry,
        "people":      parse_pipe(people_raw),
        "services":    dedupe_similar(parse_list(services_raw)),
        "assets":      clean_assets(parse_list(assets_raw)),
        "financials":  financials,
        "highlights":  highlights,
    }

# ─────────────────────────────────────────
#  STEP 3 — VISUAL NARRATION (Qwen)
# ─────────────────────────────────────────
def visual_narration(data):
    """EasyOCR reads all screenshots — reliable text extraction, no hallucination."""
    ss_paths = data.get("screenshot_paths", [])
    pages    = data.get("pages", [])
    total    = len(ss_paths)

    print(f"\n  👁️  Step 1 — Visual OCR (EasyOCR)")
    print(f"     Total screenshots : {total}")
    print(f"     Loading EasyOCR model...")

    reader = easyocr.Reader(['en'], gpu=torch.cuda.is_available(), verbose=False)
    narrations = []

    for idx, path in enumerate(ss_paths):
        if not os.path.exists(path):
            continue
        page_url = pages[idx]["url"] if idx < len(pages) else path
        print(f"     → [{idx+1}/{total}] {os.path.basename(path)}")

        narration = ask_ocr(reader, path, page_url, label=os.path.basename(path))
        n_len = len(narration) if narration else 0
        if n_len < 50:
            print(f"        ⏭  Skipped — too brief ({n_len} chars)")
        else:
            narrations.append({
                "url":       page_url,
                "page_num":  idx + 1,
                "narration": narration
            })
            print(f"        ✅ {n_len} chars extracted")

    # Free VRAM before Llama reloads for Step 4
    del reader
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print(f"\n  ✅ EasyOCR extracted {len(narrations)} pages")
    return narrations

# ─────────────────────────────────────────
#  STEP 4 — VISUAL EXTRACTION (Llama)
# ─────────────────────────────────────────
def visual_extraction(narrations, text_results, data, tagged_pages=None, skip_financials=False):
    """Llama structures OCR text for people/services/assets/financials."""
    print("\n  🔍 Step 4 — Visual extraction (Llama structures OCR text)...")
    if skip_financials:
        print("     [PDF data found] Skipping vision_financials — using PDF as source of truth")
    domain = data.get("domain", "this company")

    confirmed = [{"name": n, "title": t, "source": "Text"}
                 for n, t in text_results["people"]]

    if not narrations:
        print("     ⚠️  No narrations — skipping visual extraction")
        return {"confirmed": confirmed, "flagged": []}, {
            "services":   text_results["services"],
            "assets":     text_results["assets"],
            "financials": text_results["financials"],
        }

    # Use deterministic official-page selection; AI tagging is advisory only.
    people_urls = {p["url"] for p in select_people_pages(tagged_pages or [])}
    vision_ctx = ""
    for n in narrations:
        if not people_urls or n["url"] in people_urls:
            vision_ctx += f"=== PAGE: {n['url']} ===\n{n['narration']}\n\n"
    vision_ctx = vision_ctx[:20000]

    print("     → People from visuals...")
    v_people_raw = ask_llama(
        f"Text extracted from {domain} webpage screenshots:\n\n{vision_ctx}\n\n"
        f"List every individually named person who works AT {domain}.\n"
        f"Format: Full Name | Job Title — one per line\n"
        f"- Must be a real individual with first and last name\n"
        f"- Must have a genuine job title at {domain}\n"
        f"- EXCLUDE: single-word names, company names, department names\n"
        f"- EXCLUDE: customers, partners, people from other companies\n"
        f"- EXCLUDE: anyone whose job title names a different company as their employer (e.g. 'Chairman of XYZ Corp')\n"
        f"- CRITICAL: DO NOT use your training data. DO NOT infer or guess.\n"
        f"- CRITICAL: Only include name+title pairs explicitly written in the text above.\n"
        f"If none: NONE",
        label="vision_people"
    )
    existing_names = {n["name"].lower() for n in confirmed}
    for name, title in parse_pipe(v_people_raw):
        if name.lower() not in existing_names and not is_outsider(name, title, domain):
            confirmed.append({"name": name, "title": title, "source": "Vision"})
            existing_names.add(name.lower())

    print("     → Services from visuals...")
    v_services_raw = ask_llama(
        f"Visual descriptions of {domain} pages:\n\n{vision_ctx}\n\n"
        f"List any specific services or products visible that are NOT already in this list:\n"
        f"{chr(10).join('- ' + s for s in text_results.get('services', [])) or 'NONE'}\n\n"
        f"RULES:\n"
        f"- Only add genuinely new, specific offerings — not rephrasing of what's already listed\n"
        f"- EXCLUDE: navigation labels, section headings, vague category names, company values\n"
        f"- One per line starting with -\n"
        f"- If nothing new: NONE",
        label="vision_services"
    )

    print("     → Assets from visuals...")
    v_assets_raw = ask_llama(
        f"Visual descriptions of {domain} pages:\n\n{vision_ctx}\n\n"
        f"Assets already captured from text:\n"
        f"{chr(10).join('- ' + a for a in text_results.get('assets', [])) or 'NONE'}\n\n"
        f"List ONLY assets NOT already captured above.\n"
        f"Include company/asset name, capacity and location where shown.\n"
        f"One per line starting with -\n"
        f"If nothing new: NONE",
        label="vision_assets",
        num_predict=1500
    )

    # Build a separate context for financials — only pages tagged financials, not people pages
    fin_urls = {p["url"] for p in (tagged_pages or []) if "financials" in p.get("tags", [])}
    financials_vision_ctx = ""
    for n in narrations:
        if n["url"] in fin_urls:
            financials_vision_ctx += f"=== PAGE: {n['url']} ===\n{n['narration']}\n\n"
    financials_vision_ctx = financials_vision_ctx[:15000]

    print("     → Financials from visuals...")
    if skip_financials:
        v_finance_raw = "NONE"
        print("     [Skip] PDF financials take priority over OCR")
    elif financials_vision_ctx.strip():
        v_finance_raw = ask_llama(
            f"OCR text from {domain} financial/about pages:\n\n{financials_vision_ctx}\n\n"
            f"Extract ONLY monetary figures where BOTH a currency symbol ($, £, €, USD, AED, SAR, OMR, BHD) AND a numeric amount appear together.\n"
            f"EXCLUDE: phone numbers, energy capacity (MW/GW/kWh/MWp/kWp), percentages, headcount, dates, postal codes, addresses, plain numbers without currency.\n"
            f"FORMAT: [context]: [currency symbol][amount] — e.g. 'Funding round: $500M'\n"
            f"One per line starting with -\n"
            f"If no qualifying monetary figures: NONE",
            label="vision_financials"
        )
    else:
        v_finance_raw = "NONE"
        print("     [Skip] No financials-tagged pages with OCR")

    merged = {}
    for key, raw, existing in [
        ("services",   v_services_raw,  text_results["services"]),
        ("assets",     v_assets_raw,    text_results["assets"]),
        ("financials", v_finance_raw,   text_results["financials"]),
    ]:
        combined = list(existing)
        exist_l  = {x.lower() for x in combined}
        items = parse_list(raw)
        if key == "assets":
            items = clean_assets(items)
        for item in items:
            if item.lower() in exist_l:
                continue
            if key == "assets":
                # Extract entity name = everything before first | or , to catch format differences
                import re as _re
                entity = _re.split(r'[|,]', item)[0].strip().lower()
                entity_tokens = set(entity.split())
                # Skip if any existing item shares 2+ tokens with this entity (dedup ALL CAPS duplicates)
                is_dup = False
                for ex in exist_l:
                    ex_tokens = set(_re.split(r'[|,]', ex)[0].strip().split())
                    if len(entity_tokens & ex_tokens) >= 2:
                        is_dup = True
                        break
                if is_dup:
                    continue
            combined.append(item)
            exist_l.add(item.lower())
        if key == "services":
            combined = dedupe_similar(combined)
        if key == "financials":
            import re as _re
            # Hard filter: only keep items that contain a currency symbol + a number together
            currency_pattern = _re.compile(r'(\$|£|€|USD|AED|SAR|OMR|BHD|KWD|QAR)\s*[\d,\.]+|[\d,\.]+\s*(USD|AED|SAR|OMR|BHD|KWD|QAR)', _re.IGNORECASE)
            combined = [f for f in combined if currency_pattern.search(f)]
        merged[key] = combined

    text_count   = sum(1 for p in confirmed if p["source"] == "Text")
    vision_count = sum(1 for p in confirmed if p["source"] == "Vision")
    print(f"     👤 People: {len(confirmed)} ({text_count} text, {vision_count} vision)")

    return {"confirmed": confirmed, "flagged": []}, merged

# ─────────────────────────────────────────
#  STEP 5 — BUILD EXCEL
# ─────────────────────────────────────────
def build_excel(data, text_r, verified, merged, out_path, doc_extracted=None):
    wb = Workbook()
    ws = wb.active
    ws.title = "Research Report"
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 48
    ws.column_dimensions["C"].width = 28
    ws.column_dimensions["D"].width = 16
    ws.column_dimensions["E"].width = 14

    row = banner(ws, 1, f"  Company Research — {data.get('domain','')}")
    row = divider(ws, row)

    row = section(ws, row, "  📌  Overview")
    row = kv(ws, row, "Domain",     data.get("domain"),       alt=True)
    row = kv(ws, row, "Base URL",   data.get("base_url"),     alt=False)
    row = kv(ws, row, "Page Title", data.get("page_title"),   alt=True)
    row = kv(ws, row, "Industry",   text_r.get("industry"),   alt=False)
    row = kv(ws, row, "Emails",     ", ".join(data.get("emails",[])), alt=True)
    row = kv(ws, row, "Phones",     ", ".join(data.get("phones",[])), alt=False)
    for i,(p,u) in enumerate(data.get("social_links",{}).items()):
        row = kv(ws, row, p, u, alt=i%2==0)
    row = divider(ws, row)

    row = section(ws, row, "  🏢  What The Company Does")
    ws.row_dimensions[row].height = 80
    cell(ws, row, 1, "", bg=WHITE)
    c = cell(ws, row, 2, text_r.get("description",""))
    c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=5)
    row += 1
    row = divider(ws, row)

    row = section(ws, row, "  👤  Leadership & Key People")
    ws.row_dimensions[row].height = 18
    for col, lbl in [(1,""),(2,"Name"),(3,"Title / Role"),(4,"Source"),(5,"Status")]:
        c = ws.cell(row=row, column=col, value=lbl)
        c.font  = Font(bold=True, color=WHITE, size=11, name="Calibri")
        c.fill  = PatternFill("solid", fgColor=DARK_BLUE)
        c.alignment = Alignment(horizontal="left", vertical="center")
    row += 1

    confirmed = verified.get("confirmed", [])
    flagged   = verified.get("flagged",   [])

    for i, p in enumerate(confirmed):
        bg = GREEN_LIGHT if i%2==0 else WHITE
        ws.row_dimensions[row].height = 18
        cell(ws, row, 1, "",          bg=bg)
        cell(ws, row, 2, p["name"],   bg=bg, bold=True, fg=GREEN_DARK)
        cell(ws, row, 3, p["title"],  bg=bg)
        cell(ws, row, 4, p["source"], bg=bg)
        cell(ws, row, 5, "Confirmed", bg=bg, fg=GREEN_DARK, bold=True)
        row += 1

    for p in flagged:
        ws.row_dimensions[row].height = 18
        cell(ws, row, 1, "",          bg=YELLOW)
        cell(ws, row, 2, p["name"],   bg=YELLOW, bold=True, fg=YELLOW_DARK)
        cell(ws, row, 3, p["title"],  bg=YELLOW, fg=YELLOW_DARK)
        cell(ws, row, 4, p["source"], bg=YELLOW, fg=YELLOW_DARK)
        cell(ws, row, 5, "⚠ Review", bg=YELLOW, fg=YELLOW_DARK, bold=True)
        row += 1

    if not confirmed and not flagged:
        row = list_rows(ws, row, ["None detected"])
    row = divider(ws, row)

    row = section(ws, row, "  🛠️  Services & Products")
    row = list_rows(ws, row, merged.get("services",[])); row = divider(ws, row)

    row = section(ws, row, "  🏗️  Assets & Subsidiaries")
    row = list_rows(ws, row, merged.get("assets",[])); row = divider(ws, row)

    row = section(ws, row, "  💰  Financial Data")
    row = list_rows(ws, row, merged.get("financials",[])); row = divider(ws, row)

    row = section(ws, row, "  🏆  Key Facts & Highlights")
    row = list_rows(ws, row, text_r.get("highlights",[])); row = divider(ws, row)

    # ── Report-Based Financials (PDF sourced) ──
    if doc_extracted and any(doc_extracted.get(k) for k in ("financials","financial_trends","financial_health","esg","sustainability")):
        row = section(ws, row, "  📊  Report-Based Financials")
        kv(ws, row, "", "Source: Annual Reports / Financial Statements / ESG Reports", alt=False)
        row += 1
        if doc_extracted.get("financial_trends"):
            row = section(ws, row, "  📈  Company Health Over Time")
            row = list_rows(ws, row, doc_extracted["financial_trends"]); row = divider(ws, row)
        if doc_extracted.get("financial_health"):
            row = section(ws, row, "  🧾  Financial Health Assessment")
            row = list_rows(ws, row, doc_extracted["financial_health"]); row = divider(ws, row)
        if doc_extracted.get("financials"):
            row = section(ws, row, "  💰  Financial Figures")
            row = list_rows(ws, row, doc_extracted["financials"]); row = divider(ws, row)
        if doc_extracted.get("esg"):
            row = section(ws, row, "  🌱  ESG Ratings & Certifications")
            row = list_rows(ws, row, doc_extracted["esg"]); row = divider(ws, row)
        if doc_extracted.get("sustainability"):
            row = section(ws, row, "  ♻️  Sustainability & Green Energy Metrics")
            row = list_rows(ws, row, doc_extracted["sustainability"]); row = divider(ws, row)

    row = section(ws, row, "  ✅  Pages Crawled")
    row = list_rows(ws, row, [p["url"] for p in data.get("pages",[])])

    ws.freeze_panes = "A2"

    ws2 = wb.create_sheet("Screenshots")
    ws2.column_dimensions["A"].width = 100
    banner(ws2, 1, "  📸  Page Screenshots", ncols=1)
    ss_row = 2
    for i, ss_path in enumerate(data.get("screenshot_paths",[])[:25]):
        if not os.path.exists(ss_path): continue
        url = data["pages"][i]["url"] if i < len(data.get("pages",[])) else ss_path
        c = ws2.cell(row=ss_row, column=1, value=url)
        c.font = Font(bold=True, size=10, color=DARK_BLUE)
        ss_row += 1
        try:
            img   = XLImage(ss_path)
            scale = min(900/img.width, 1.0) if img.width > 0 else 1
            img.width  = int(img.width  * scale)
            img.height = int(img.height * scale)
            ws2.add_image(img, f"A{ss_row}")
            ws2.row_dimensions[ss_row].height = img.height * 0.75
            ss_row += int(img.height/14) + 3
        except Exception as e:
            ws2.cell(row=ss_row, column=1, value=f"[Image error: {e}]")
            ss_row += 2

    wb.save(out_path)
    print(f"\n  ✅ Report saved: {out_path}\n")

# ─────────────────────────────────────────
#  RUN
# ─────────────────────────────────────────
if __name__ == "__main__":
    prevent_sleep()

    # FIX: search only one level deep to avoid mixing JSONs from other domains
    json_files = sorted(SAVE_DIR.glob("*/*_research.json"))

    if not json_files:
        path = Path(input("Paste full path to JSON:\n> ").strip().strip('"'))
    elif len(json_files) == 1:
        path = json_files[0]
        print(f"Found: {path}")
    else:
        print("Found multiple research files:")
        for i, f in enumerate(json_files):
            print(f"  [{i+1}] {f.parent.name} — {f.name}")
        path = json_files[int(input("Pick a number: "))-1]

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    log_path   = init_log(data.get("domain","unknown"))
    run_start  = time.time()
    step_times = {}

    def tick(label):
        step_times[label] = time.time()

    def tock(label):
        if label in step_times:
            elapsed = time.time() - step_times[label]
            print(f"     ⏱  {label}: {elapsed/60:.1f} min ({elapsed:.0f}s)")

    # Step 1 — Visual OCR first (EasyOCR, frees VRAM before Llama loads)
    tick("Step 1 OCR")
    narrations = visual_narration(data)
    tock("Step 1 OCR")

    # Step 1.5 — PDF reading (PyMuPDF, CPU only, before Llama loads)
    tick("Step 1.5 PDF")
    research_folder = str(path).replace(path.name, "").rstrip("/\\") if hasattr(path, "name") else str(Path(path).parent)
    doc_results = read_documents(research_folder)
    tock("Step 1.5 PDF")

    # Step 2 — Tag all pages (scraped text + OCR text)
    tick("Step 2 Tagging")
    tagged_pages = tag_pages(data, narrations)
    tock("Step 2 Tagging")

    # Step 3 — Text extraction
    tick("Step 3 Text")
    text_results = text_extraction(data, tagged_pages, narrations=narrations)
    tock("Step 3 Text")

    # Step 4 — Visual extraction (Llama structures OCR text)
    tick("Step 4 Visual")
    has_pdf_financials = any(d.get("is_report") and d.get("financial_chunks") for d in doc_results)
    verified, merged = visual_extraction(narrations, text_results, data, tagged_pages=tagged_pages,
                                         skip_financials=has_pdf_financials)
    tock("Step 4 Visual")

    # Step 4.5 — PDF document extraction
    tick("Step 4.5 PDF Extract")
    doc_extracted = extract_from_documents(doc_results, data.get("domain", ""))
    tock("Step 4.5 PDF Extract")

    # Step 5 — Build Excel
    out = str(path).replace(".json", "_REPORT.xlsx")
    build_excel(data, text_results, verified, merged, out, doc_extracted=doc_extracted)
    close_log()

    total_mins = (time.time() - run_start) / 60
    print(f"  👤 People: {len(verified.get('confirmed',[]))} confirmed")
    print(f"  🛠️  Services: {len(merged.get('services',[]))}")
    print(f"  💰 Financials: {len(merged.get('financials',[]))}")
    print(f"  🏗️  Assets: {len(merged.get('assets',[]))}")
    print(f"  📋 Log: {log_path}")
    print(f"  ⏱  Total run time: {total_mins:.1f} min\n")

    allow_sleep()

    # Write completion marker so Claude can detect the run is done
    marker = str(path).replace(".json", "_DONE.txt")
    with open(marker, "w") as f:
        f.write("DONE")
    input("Done! Press Enter to close.")
