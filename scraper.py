import argparse
import csv
import logging
import os
import re
import sys
import time
from datetime import datetime
from typing import Dict, Iterable, List, Optional
from urllib.parse import urljoin, quote

import requests
from bs4 import BeautifulSoup, Tag


BASE_URL = "https://students.yale.edu"

COLLEGE_NAMES = {
    "Benjamin Franklin College", "Berkeley College", "Branford College",
    "Davenport College", "Ezra Stiles College", "Grace Hopper College",
    "Jonathan Edwards College", "Morse College", "Pauli Murray College",
    "Pierson College", "Saybrook College", "Silliman College",
    "Timothy Dwight College", "Trumbull College", "Yale College",
}

MAJOR_KEYWORDS = re.compile(
    r"(?i)(engineering|science|studies|econom|biology|bio|math|mathematics|history|english|"
    r"psychology|sociology|philosophy|political|global|chemical|electrical|mechanical|civil|"
    r"applied|neuro|physics|chemistry|art|architecture|music|theater|theatre|film|media|stat|"
    r"statistics|computer|cs\b|finance|anthropology|linguistics|literature|german|french|spanish|"
    r"italian|portuguese|russian|slav|judaic|hebrew|korean|japanese|chinese|latin|greek|classics|"
    r"environment|earth|geology|astronomy|religion|history of|east|afric|american|asian)"
)

# ---------- Logging ----------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ---------- Helpers ----------

def _parse_cookie_file(path: str) -> str:
    import re
    txt = open(path, "r", encoding="utf-8").read().strip()
    if not txt:
        raise RuntimeError(f"{path} is empty")

    m = re.search(r"(?im)^\s*cookie\s*:\s*(.+)$", txt)
    if m:
        return m.group(1).strip()

    if "\t" in txt and "\n" in txt:
        pairs = []
        for line in txt.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                name, value = parts[5], parts[6]
                if name and value:
                    pairs.append(f"{name}={value}")
        if pairs:
            return "; ".join(pairs)

    lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    if len(lines) > 1 and all("=" in ln for ln in lines):
        return "; ".join(lines)

    return txt.strip()


def load_cookie_string(env_var: str, cookies_file: Optional[str]) -> str:
    if cookies_file:
        return _parse_cookie_file(cookies_file)
    s = os.getenv(env_var)
    if not s:
        if os.path.exists("cookies.txt"):
            return _parse_cookie_file("cookies.txt")
        raise RuntimeError(
            "No cookies provided. Set YALE_FB_COOKIES or pass --cookies-file (or create ./cookies.txt)."
        )
    return s.strip()


def get_session(cookies_str: str) -> requests.Session:
    session = requests.Session()
    for pair in cookies_str.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        session.cookies.set(name.strip(), value.strip())
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        )
    })
    return session

def fetch(session: requests.Session, url: str, retries: int = 3, backoff: float = 1.5) -> Optional[requests.Response]:
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=20)
            if r.status_code == 200:
                return r
            logging.warning(f"Fetch attempt {attempt} got HTTP {r.status_code} for {url}")
            if r.status_code in (403, 401):
                return r
        except requests.RequestException as e:
            logging.warning(f"Fetch attempt {attempt} failed: {e}")
        time.sleep(backoff ** attempt)
    return None

def find_college_name(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    sel = soup.select_one("#college_select option[selected]")
    return sel.get_text(strip=True) if sel else "Unknown"

def get_next_page_url(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "lxml")
    nxt = soup.select_one("div.next > a") or soup.select_one("nav .next a")
    if not nxt:
        nxt = next((a for a in soup.find_all("a") if a.get_text(strip=True).lower().startswith("next")), None)
    return nxt["href"] if (nxt and nxt.has_attr("href")) else None

def parse_student_card(card: Tag, page_college: str) -> Dict[str, Optional[str]]:
    rec: Dict[str, Optional[str]] = {
        "name": None,
        "college": page_college,
        "class_year": None,
        "major": None,
        "bio": None,
        "source_url": None,
        "scraped_at": datetime.utcnow().isoformat(),
    }

    # Name
    name_tag = card.select_one("div.student_name > h5")
    if name_tag:
        rec["name"] = name_tag.get_text(strip=True)

    # Year: '27 or ’27
    year_tag = card.select_one("div.student_year")
    if year_tag:
        rec["class_year"] = year_tag.get_text(strip=True).lstrip("’'")

    lines: List[str] = []
    for info in card.select("div.student_info"):
        for br in info.find_all("br"):
            br.replace_with("\n")
        text = info.get_text("\n", strip=True)
        if text:
            lines.extend(ln.strip() for ln in text.split("\n") if ln.strip())

    if not lines:
        return rec

    # helpers
    MONTHS = {"Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"}
    def looks_like_birthday(s: str) -> bool:
        parts = s.replace(".", "").split()
        return len(parts) >= 1 and parts[0][:3] in MONTHS
    def looks_like_address(s: str) -> bool:
        return any(ch.isdigit() for ch in s) or "/" in s

    for i, ln in enumerate(list(lines)):
        if ln in COLLEGE_NAMES:
            rec["college"] = ln
            del lines[i]
            break

    if lines and looks_like_birthday(lines[-1]):
        lines.pop()

    major = None
    candidates = [ln for ln in lines if not looks_like_address(ln) and ln not in COLLEGE_NAMES]
    for ln in reversed(candidates):
        if ln.lower() == "undeclared":
            major = "Undeclared"
            break
        if MAJOR_KEYWORDS.search(ln) or re.fullmatch(r"[A-Za-z,&' \-]{3,}", ln):
            major = ln
            break
    rec["major"] = major

    bio_lines = [ln for ln in lines if ln != major] if major else lines
    rec["bio"] = "; ".join(bio_lines) if bio_lines else None

    return rec

def parse_directory_page(html: str, college: str, debug_n: int = 0) -> List[Dict[str, Optional[str]]]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("div.student_container")
    results: List[Dict[str, Optional[str]]] = []
    for idx, card in enumerate(cards):
        rec = parse_student_card(card, college)
        results.append(rec)
        if debug_n and idx < debug_n:
            info_tag = card.select_one("div.student_info")
            if info_tag:
                for br in info_tag.find_all("br"):
                    br.replace_with("\n")
                dbg = [ln.strip() for ln in info_tag.get_text("\n", strip=True).split("\n") if ln.strip()]
            else:
                dbg = []
            logging.info(f"[DEBUG] {rec.get('name')}: lines={dbg} -> major={rec.get('major')}")
    return results

def write_csv(records: List[Dict[str, Optional[str]]], out_path: str) -> None:
    if not records:
        logging.warning("No records to write")
        return
    fieldnames = ["name","college","class_year","major","bio","source_url","scraped_at"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    logging.info(f"Wrote {len(records)} records to {out_path}")

def scrape_directory(session: requests.Session, start_url: str, max_pages: Optional[int], delay: float, debug_save: bool, debug_print: int) -> List[Dict[str, Optional[str]]]:
    records: List[Dict[str, Optional[str]]] = []
    current_url = start_url
    pages_scraped = 0
    while current_url:
        logging.info(f"Fetching {current_url}")
        resp = fetch(session, current_url)
        if not resp:
            logging.warning(f"Failed to fetch {current_url}")
            break
        if resp.status_code == 302:
            logging.error("Redirected to login — cookies likely expired. Recopy cookies and try again.")
            break
        html = resp.text
        current_url = resp.url  

        if debug_save:
            with open(f"debug_page_{pages_scraped:03d}.html", "w", encoding="utf-8") as f:
                f.write(html)

        college_name = find_college_name(html)
        page_records = parse_directory_page(html, college_name, debug_n=debug_print)
        for rec in page_records:
            rec["source_url"] = current_url
        records.extend(page_records)

        pages_scraped += 1
        if max_pages is not None and pages_scraped >= max_pages:
            logging.info(f"Reached max-pages = {max_pages}")
            break

        next_rel = get_next_page_url(html)
        if next_rel:
            current_url = urljoin(current_url, next_rel)
            time.sleep(max(0.0, float(delay)))
        else:
            logging.info("No further pages found")
            break
    return records

def main(argv: Optional[Iterable[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Scrape Yale Facebook card view (/facebook/PhotoPageNew).")
    p.add_argument("--out", default="students.csv", help="Output CSV filename")
    p.add_argument("--college", default=None, help="Residential college to switch to before scraping (e.g. 'Pierson College')")
    p.add_argument("--start", dest="start_url", default=None, help="Start URL (defaults to /facebook/PhotoPageNew?currentIndex=0)")
    p.add_argument("--max-pages", type=int, default=None, help="Maximum number of pages to scrape")
    p.add_argument("--delay", type=float, default=1.0, help="Delay (seconds) between pages")
    p.add_argument("--cookies-file", default=None, help="Path to a file containing the Cookie header value")
    p.add_argument("--debug-save", action="store_true", help="Save each fetched page to debug_page_###.html")
    p.add_argument("--debug-print", type=int, default=0, help="Print parsed info lines for first N cards per page")

    args = p.parse_args(argv)

    try:
        cookie_str = load_cookie_string("YALE_FB_COOKIES", args.cookies_file)
    except Exception as e:
        logging.error(str(e))
        return 1

    session = get_session(cookie_str)

    if args.start_url:
        start_url = urljoin(BASE_URL, args.start_url)
    else:
        if args.college:
            start_url = urljoin(BASE_URL, f"/facebook/ChangeCollege?newOrg={quote(args.college)}")
        else:
            start_url = urljoin(BASE_URL, "/facebook/PhotoPageNew?currentIndex=0")

    records = scrape_directory(session, start_url, max_pages=args.max_pages, delay=args.delay, debug_save=args.debug_save, debug_print=args.debug_print)
    write_csv(records, args.out)
    return 0

if __name__ == "__main__":
    sys.exit(main())
