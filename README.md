# Yale Facebook Scraper

Scrapes publicly available fields (no photos) from Yale’s online Facebook/directory **card view**:

- `name`
- `college` (per-student residential college)
- `class_year` (e.g., `27`)
- `major`
- `bio` (leftover lines like room/addr/city; birthday removed)
- `source_url`
- `scraped_at` (UTC ISO timestamp)

**Output:** `students.csv` with this exact header order:
```
name,college,class_year,major,bio,source_url,scraped_at
```

> You must already have access to Yale Facebook and use your own account. This tool never asks for your NetID/password; it uses the browser **cookies** you copy yourself.

---

## Features

- Scrapes the **“view all”** variant which includes all students
- Reads **both** info blocks per card (first = college, second = address/major/birthday)
- Heuristic **major extraction** (supports “Undeclared” and combos like “CS & Econ”)
- **Birthday** is removed from output; remaining lines become `bio`
- Handles curly year marks (`’27`) and diacritics
- Robust **“next page”** detection (desktop & mobile pagers), with a safe fallback

---

## Requirements

- Python 3.8+ (Windows, macOS, Linux, or WSL)
- Install deps from `requirements.txt`:
  - `requests`
  - `beautifulsoup4`
  - `lxml`

---

## Install

### Windows (PowerShell)
```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```
If `py` isn’t found, use `python` instead. You can call the venv’s Python directly (no need to run `Activate.ps1`).

### macOS / Linux / WSL
```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

---

## Get your cookies (Chrome or Edge)

1. Log in and open:  
   `https://students.yale.edu/facebook/PhotoPageNew?currentIndex=0`
2. Select Yale College as the college and then **View all**. We want all students to be in one page for an easier scraping.
3. Open DevTools (**F12**) → **Network** → make sure recording is on (red dot) → reload.
4. Click the **document** request for that URL → **Headers** → copy the **cookie** header value.
5. Paste into a file named **`cookies.txt`** as **one single line**, semicolon-separated.  
   Do **not** include the `cookie:` prefix.

**Which cookies do I need?**
- **MUST HAVE:** `JSESSIONID=...`,`dtCookie`, `dtPC`, `nmstat`, `rxVisitor`, `rxvt`, `fpestid`

**Example `cookies.txt` (one line):**
```
JSESSIONID=F6A04B87D3FF34FC23301DADF74FFF13; dtCookie=v_4_srv_...; dtPC=1$212429456_259h-...; dtSa=-; fpestid=5Iv8aDn...; nmstat=bea04ea7-...; rxVisitor=17570425...; rxvt=1758214270587|1758211734016
```
**MAKE SURE THERE ARE NO NEW LINES IN `cookies.txt`**

> The scraper auto-uses `./cookies.txt` if present. You can also pass `--cookies-file path`.

---

## Run it

**Windows (PowerShell)**
```powershell
.\.venv\Scripts\python.exe .\scraper.py --cookies-file .\cookies.txt --start "https://students.yale.edu/facebook/PhotoPageNew?currentIndex=-1&numberToGet=-1" --max-pages 1 --out students.csv
```

**macOS/Linux/WSL**
```bash
python3 scraper.py --cookies-file cookies.txt --start 'https://students.yale.edu/facebook/PhotoPageNew?currentIndex=-1&numberToGet=-1' --max-pages 1 --out students.csv
```

---

## Output parsing notes

- Some cards genuinely omit majors.
- The scraper:
  - reads **both** `div.student_info` blocks per card,
  - removes the per-student college line,
  - strips the trailing birthday (e.g., `Dec 29`),
  - infers the **major** from remaining lines (keywords + heuristics),
  - joins leftover lines into **`bio** (e.g., room/addr/city).

**Sample CSV row**

"Bylykbashi, Andrea",Pierson College,28,Undeclared,"Rruga Mine Peza 256/3; Tirana, 1001; Albania",https://students.yale.edu/facebook/PhotoPageNew?currentIndex=0,2025-09-18T16:35:21.657160

The scraped csv file has also been included for completion sake.

## Next Steps

After all students' information has been retrieved, one can perform post processing on the csv file, filter by major, college, graduation date etc., and create more targeted csv files for their intended use.
