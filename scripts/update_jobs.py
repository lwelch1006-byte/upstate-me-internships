#!/usr/bin/env python3
import hashlib
import html
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
APP_ID = os.getenv("ADZUNA_APP_ID", "")
APP_KEY = os.getenv("ADZUNA_APP_KEY", "")
USER_AGENT = "Mozilla/5.0 (compatible; UpstateMEInternships/2.0; +https://github.com/lwelch1006-byte/upstate-me-internships)"

UPSTATE_PLACES = [
    "greenville","greer","simpsonville","mauldin","fountain inn","piedmont","easley",
    "travelers rest","taylors","duncan","lyman","wellford","spartanburg","inman",
    "woodruff","roebuck","boiling springs","moore","cowpens","gaffney","gray court",
    "laurens","anderson","pendleton","clemson","seneca","pickens","liberty","belton",
    "pelzer","westminster","central"
]
PLACE_LABELS = {
    "greenville":"Greenville, SC","greer":"Greer, SC","simpsonville":"Simpsonville, SC",
    "mauldin":"Mauldin, SC","fountain inn":"Fountain Inn, SC","piedmont":"Piedmont, SC",
    "easley":"Easley, SC","travelers rest":"Travelers Rest, SC","taylors":"Taylors, SC",
    "duncan":"Duncan, SC","lyman":"Lyman, SC","wellford":"Wellford, SC",
    "spartanburg":"Spartanburg, SC","inman":"Inman, SC","woodruff":"Woodruff, SC",
    "roebuck":"Roebuck, SC","boiling springs":"Boiling Springs, SC","moore":"Moore, SC",
    "cowpens":"Cowpens, SC","gaffney":"Gaffney, SC","gray court":"Gray Court, SC",
    "laurens":"Laurens, SC","anderson":"Anderson, SC","pendleton":"Pendleton, SC",
    "clemson":"Clemson, SC","seneca":"Seneca, SC","pickens":"Pickens, SC",
    "liberty":"Liberty, SC","belton":"Belton, SC","pelzer":"Pelzer, SC",
    "westminster":"Westminster, SC","central":"Central, SC"
}

LARGE = {
    "ge vernova","michelin","bmw","bmw group","jacobs","vertiv","milliken","zf",
    "opmobility","op mobility","illinois tool works","itw","hubbell","bosch",
    "lockheed martin","fluor","magna","afl","duke energy","eaton","borgwarner",
    "jtekt","3m","basf","siemens","electrolux","arthrex","timken","sealed air",
    "keirig dr pepper","keurig dr pepper","daimler truck","freightliner"
}
SMALL = {
    "air compressor services","acs","ktm solutions","schot engineers","h2l",
    "tfs engineers","peritus engineers","engineering design services","dwg",
    "eliant engineering","devita","aesolutions","itac","jedson"
}

# Extra employer career pages supplement the companies already displayed on the site.
EXTRA_EMPLOYERS = {
    "Lockheed Martin":"https://www.lockheedmartinjobs.com/",
    "Fluor":"https://www.fluor.com/careers",
    "Burns & McDonnell":"https://www.burnsmcd.com/careers",
    "Salas O'Brien":"https://salasobrien.com/careers/",
    "Day & Zimmermann":"https://www.dayzim.com/careers/",
    "Magna":"https://jobs.magna.com/",
    "Bosch":"https://www.bosch.us/careers/",
    "JTEKT":"https://careers.jtekt-na.com/",
    "AFL":"https://www.aflglobal.com/en/Company/Careers",
    "Sealed Air":"https://jobs.sealedair.com/",
    "Current Lighting":"https://www.currentlighting.com/careers",
    "KYOCERA AVX":"https://www.kyocera-avx.com/careers/",
    "Yanfeng":"https://www.yanfeng.com/careers",
    "Fuyao Glass America":"https://fuyaousa.com/careers/",
    "TTI":"https://www.ttigroup.com/careers/",
    "Electrolux":"https://career.electroluxgroup.com/",
    "First Quality":"https://careers.firstquality.com/",
    "Arthrex":"https://careers.arthrex.com/",
    "Pregis":"https://www.pregis.com/careers/",
    "Glen Raven":"https://www.glenraven.com/careers/",
    "BorgWarner":"https://jobs.borgwarner.com/",
    "Timken":"https://careers.timken.com/",
    "Duke Energy":"https://careers.duke-energy.com/",
    "Element Materials Technology":"https://element.com/careers",
    "Toray Composite Materials":"https://www.toraycma.com/careers/",
    "Bausch + Lomb":"https://careers.bausch.com/"
}

def fetch_text(url, timeout=15):
    req = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"
    })
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")

def fetch_json(url, timeout=20):
    return json.loads(fetch_text(url, timeout=timeout))

def strip_html(value):
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", value).strip()

def relevant(title, desc=""):
    """
    Keep internships that are a realistic fit for a mechanical-engineering student.
    The title is weighted much more heavily than the description so unrelated jobs
    do not get admitted just because an employer page mentions "engineering".
    """
    title_l = strip_html(title).lower()
    desc_l = strip_html(desc).lower()
    text = title_l + " " + desc_l

    internship = any(x in text for x in [
        "intern","internship","co-op","coop","co op","student engineer",
        "engineering student","summer engineering","spring engineering"
    ])
    if not internship:
        return False

    # Reject clearly non-ME functions even when their descriptions contain
    # generic engineering/company language.
    excluded_title_terms = [
        "marketing","communications","public relations","social media","sales intern",
        "business intern","finance","accounting","human resources","hr intern",
        "recruiting","talent acquisition","first aid","nursing","medical","pharmacy",
        "environmental health","health & safety","health and safety","ehs intern",
        "hse intern","safety intern","information technology","it intern",
        "cybersecurity","software intern","software engineering","computer science",
        "data science","data analyst","legal intern","law intern","procurement intern"
    ]
    if any(term in title_l for term in excluded_title_terms):
        return False

    # Strong ME / ME-adjacent signals in the title. These are the roles a
    # mechanical-engineering student would reasonably target.
    allowed_title_terms = [
        "mechanical","manufacturing engineer","manufacturing engineering",
        "process engineer","process engineering","quality engineer","quality engineering",
        "design engineer","design engineering","product engineer","product engineering",
        "test engineer","test engineering","validation engineer","validation engineering",
        "reliability engineer","reliability engineering","sustaining engineer",
        "automation engineer","automation engineering","controls engineer","controls engineering",
        "mechatronic","thermal engineer","thermal engineering","hvac",
        "maintenance engineer","maintenance engineering","tooling engineer",
        "tooling engineering","industrial engineer","industrial engineering",
        "packaging engineer","packaging engineering","technical planning",
        "facilities engineer","facilities engineering","r&d engineer","research engineer"
    ]
    if any(term in title_l for term in allowed_title_terms):
        return True

    # Generic titles such as "Engineering Intern" or "Project Engineering Intern"
    # only qualify when the description contains a strong mechanical signal.
    generic_engineering_title = any(term in title_l for term in [
        "engineering intern","engineer intern","engineering co-op","engineering coop",
        "project engineering","project engineer","quality intern","process intern",
        "product intern","design intern","test intern","reliability intern"
    ])
    mechanical_desc_signals = [
        "mechanical engineering","mechanical design","manufacturing engineering",
        "manufacturing process","cad","solidworks","creo","catia","autocad",
        "gd&t","geometric dimensioning","tooling","fixture","machining","cnc",
        "thermodynamics","heat transfer","fluid mechanics","thermal","hvac",
        "piping","rotating equipment","equipment design","product design",
        "prototype","prototyping","test engineering","validation testing",
        "reliability engineering","root cause","continuous improvement",
        "lean manufacturing","automation","robotics","plc","mechatronics"
    ]
    return generic_engineering_title and any(term in desc_l for term in mechanical_desc_signals)

def is_upstate(text):
    t = (text or "").lower()
    return any(place in t for place in UPSTATE_PLACES) and (
        "sc" in t or "south carolina" in t or any(place in t for place in UPSTATE_PLACES)
    )

def is_summer_2027(title, desc=""):
    """
    Only allow roles clearly tied to Summer 2027.
    Reject Spring/Fall terms and ambiguous postings with no explicit Summer 2027 signal.
    """
    text = (strip_html(title) + " " + strip_html(desc)).lower()

    # Explicit non-summer 2027 terms are always rejected.
    if re.search(r"\b(spring|fall|autumn)\s*(?:20)?27\b", text):
        return False
    if re.search(r"\b(?:20)?27\s*(spring|fall|autumn)\b", text):
        return False

    summer_patterns = [
        r"\bsummer\s*2027\b",
        r"\b2027\s*summer\b",
        r"\bsummer\s*['’]?27\b",
        r"\b['’]?27\s*summer\b",
        r"\bsummer\s+intern(?:ship)?[^.]{0,40}\b2027\b",
        r"\b2027\b[^.]{0,40}\bsummer\s+intern(?:ship)?\b",
        r"\bmay\s*(?:-|–|to|through)\s*(?:august|aug)\s*2027\b",
        r"\bmay\s*2027\b[^.]{0,50}\b(?:august|aug)\s*2027\b"
    ]
    return any(re.search(p, text) for p in summer_patterns)

def infer_location(text):
    t = (text or "").lower()
    for place in UPSTATE_PLACES:
        if place in t:
            return PLACE_LABELS.get(place, place.title() + ", SC")
    return "Upstate SC"

def classify_type(title, desc=""):
    t = (title + " " + desc).lower()
    rules = [
        ("Manufacturing", ["manufacturing","industrialization","technical planning","production engineering"]),
        ("Quality", ["quality","supplier quality","dimensional","metrology"]),
        ("Process", ["process engineering","process engineer","continuous improvement"]),
        ("Automation", ["automation","controls","robotics","mechatronics","plc"]),
        ("Reliability", ["reliability","sustaining","maintenance engineering"]),
        ("Test", ["test engineering","validation","verification","test intern"]),
        ("R&D", ["r&d","research and development","research & development"]),
        ("Design", ["design engineer","mechanical design","product engineering","product development"]),
        ("Mechanical", ["mechanical","thermal","hvac","fluid","piping"]),
        ("Project", ["project","facilities","engineering intern","engineering co-op"]),
    ]
    for label, words in rules:
        if any(w in t for w in words):
            return label
    return "Project"

def classify_size(company):
    c = re.sub(r"[^a-z0-9 &+]+", "", (company or "").lower()).strip()
    if any(x in c for x in SMALL):
        return "small"
    if any(x in c for x in LARGE):
        return "large"
    return "other"

def term_from(text):
    t = (text or "").lower()
    for season in ["summer","spring","fall"]:
        m = re.search(rf"\b{season}\s+(20\d{{2}})\b", t)
        if m:
            return season.title() + " " + m.group(1)
    m = re.search(r"\b(20\d{2})\b", t)
    return m.group(1) if m else "Current"

def summary(desc):
    s = strip_html(desc)
    if not s:
        return "Engineering internship opportunity in Upstate South Carolina."
    return s if len(s) <= 180 else s[:177].rsplit(" ", 1)[0] + "…"

def normalize(value):
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()

def dedupe_key(company, title, location):
    city = infer_location(location)
    return "|".join([normalize(company), normalize(title), normalize(city)])

def stable_id(key):
    return "job-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

def parse_iso(value):
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000 if value > 10_000_000_000 else value, tz=timezone.utc)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None

def extract_embedded():
    text = INDEX.read_text(encoding="utf-8")
    jm = re.search(r"const EMBEDDED_JOBS=(.*?);\nconst EMBEDDED_COMPANIES=", text, re.S)
    cm = re.search(r"const EMBEDDED_COMPANIES=(.*?);\nconst state=", text, re.S)
    jobs_payload = json.loads(jm.group(1)) if jm else {"jobs":[]}
    companies_payload = json.loads(cm.group(1)) if cm else {"companies":[]}
    return text, jobs_payload, companies_payload

def adzuna_search(query):
    if not APP_ID or not APP_KEY:
        return []
    params = {
        "app_id": APP_ID,
        "app_key": APP_KEY,
        "what": query,
        "where": "Greenville, SC",
        "distance": 50,
        "results_per_page": 50,
        "sort_by": "date",
        "content-type": "application/json",
    }
    url = "https://api.adzuna.com/v1/api/jobs/us/search/1?" + urlencode(params)
    return fetch_json(url, timeout=30).get("results", [])

def direct_sources(companies_payload):
    sources = {}
    for c in companies_payload.get("companies", []):
        name, url = c.get("name"), c.get("url")
        if name and url:
            sources[name] = url
    sources.update(EXTRA_EMPLOYERS)
    return sources

def discover_ats(page_html):
    gh = set()
    lever = set()
    patterns = [
        r"(?:https?:)?//(?:boards|job-boards)\.greenhouse\.io/([A-Za-z0-9_-]+)",
        r"(?:https?:)?//boards\.greenhouse\.io/embed/job_board\?for=([A-Za-z0-9_-]+)",
        r"(?:https?:)?//boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)"
    ]
    for pat in patterns:
        gh.update(re.findall(pat, page_html, re.I))
    lever.update(re.findall(r"(?:https?:)?//jobs\.lever\.co/([A-Za-z0-9_-]+)", page_html, re.I))
    return gh, lever

def scan_greenhouse(company, token):
    jobs = []
    try:
        data = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    except Exception as e:
        print("greenhouse warning", company, token, e)
        return jobs
    for item in data.get("jobs", []):
        title = strip_html(item.get("title", ""))
        loc = ((item.get("location") or {}).get("name") or "")
        desc = strip_html(item.get("content", ""))
        combined = " ".join([title, loc, desc])
        if relevant(title, desc) and is_upstate(combined):
            jobs.append({
                "company": company, "title": title, "location": infer_location(combined),
                "description": desc, "url": item.get("absolute_url") or "",
                "created": item.get("updated_at"), "source": "Employer / Greenhouse", "rank": 3
            })
    return jobs

def scan_lever(company, site):
    jobs = []
    try:
        data = fetch_json(f"https://api.lever.co/v0/postings/{site}?mode=json")
    except Exception as e:
        print("lever warning", company, site, e)
        return jobs
    if not isinstance(data, list):
        return jobs
    for item in data:
        title = strip_html(item.get("text", ""))
        cats = item.get("categories") or {}
        loc = cats.get("location") or " ".join(cats.get("allLocations") or [])
        desc = strip_html(item.get("descriptionPlain") or item.get("description") or "")
        combined = " ".join([title, loc, desc])
        if relevant(title, desc) and is_upstate(combined):
            jobs.append({
                "company": company, "title": title, "location": infer_location(combined),
                "description": desc, "url": item.get("hostedUrl") or item.get("applyUrl") or "",
                "created": item.get("createdAt"), "source": "Employer / Lever", "rank": 3
            })
    return jobs

def scan_visible_links(company, base_url, page_html):
    jobs = []
    anchor_re = re.compile(r"<a\b[^>]*?href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
    for m in anchor_re.finditer(page_html):
        href = html.unescape(m.group(1)).strip()
        title = strip_html(m.group(2))
        if not title or len(title) < 5 or len(title) > 180:
            continue
        start, end = max(0, m.start() - 400), min(len(page_html), m.end() + 400)
        context = strip_html(page_html[start:end])
        combined = title + " " + context + " " + href
        if not relevant(title, context) or not is_upstate(combined):
            continue
        full_url = urljoin(base_url, href)
        if not full_url.startswith("http"):
            continue
        jobs.append({
            "company": company, "title": title, "location": infer_location(combined),
            "description": context, "url": full_url, "created": None,
            "source": "Employer careers page", "rank": 2
        })
    return jobs

def scan_one_employer(company, url):
    found = []
    try:
        page = fetch_text(url, timeout=10)
    except Exception as e:
        print("career page warning", company, e)
        return found
    gh_tokens, lever_sites = discover_ats(page)
    for token in gh_tokens:
        found.extend(scan_greenhouse(company, token))
    for site in lever_sites:
        found.extend(scan_lever(company, site))
    found.extend(scan_visible_links(company, url, page))
    return found

def scan_employers(companies_payload):
    sources = list(direct_sources(companies_payload).items())
    found = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(scan_one_employer, company, url): company for company, url in sources}
        for future in as_completed(futures):
            company = futures[future]
            try:
                found.extend(future.result())
            except Exception as e:
                print("employer scan warning", company, e)
    return found

def convert_adzuna(item):
    title = strip_html(item.get("title") or "")
    desc = strip_html(item.get("description") or "")
    company = ((item.get("company") or {}).get("display_name") or "Unknown employer").strip()
    location = ((item.get("location") or {}).get("display_name") or "Upstate SC").strip()
    if not relevant(title, desc):
        return None
    salary = ""
    if item.get("salary_min") and item.get("salary_max"):
        salary = f"${item['salary_min']:,.0f}–${item['salary_max']:,.0f}"
    return {
        "company": company, "title": title, "location": location, "description": desc,
        "url": item.get("redirect_url") or "", "created": item.get("created"),
        "salary": salary, "source": "Adzuna", "rank": 1
    }

def main():
    source_text, old_payload, companies_payload = extract_embedded()
    old_jobs = old_payload.get("jobs", [])
    old_by_key = {dedupe_key(j.get("company"), j.get("title"), j.get("location")): j for j in old_jobs}
    now = datetime.now(timezone.utc)
    collected = {}

    def add(raw):
        if not raw:
            return
        company = (raw.get("company") or "Unknown employer").strip()
        title = strip_html(raw.get("title") or "")
        location = (raw.get("location") or "Upstate SC").strip()
        if not title or not relevant(title, raw.get("description", "")):
            return
        if not is_summer_2027(title, raw.get("description", "")):
            return
        key = dedupe_key(company, title, location)
        old = old_by_key.get(key, {})
        created = parse_iso(raw.get("created"))
        first_seen = parse_iso(old.get("first_seen")) or created or now
        existing = collected.get(key)
        job = {
            "id": old.get("id") or stable_id(key),
            "company": company,
            "title": title,
            "location": location,
            "type": classify_type(title, raw.get("description", "")),
            "company_size": classify_size(company),
            "term": term_from(title + " " + raw.get("description", "")),
            "salary": raw.get("salary", ""),
            "summary": summary(raw.get("description", "")),
            "apply_url": raw.get("url") or old.get("apply_url") or "",
            "is_new": (now - first_seen) <= timedelta(days=7),
            "first_seen": first_seen.isoformat(),
            "last_seen": now.isoformat(),
            "source": raw.get("source", "Public posting")
        }
        if not existing or raw.get("rank", 0) > existing.get("_rank", 0):
            job["_rank"] = raw.get("rank", 0)
            collected[key] = job

    # Direct employer sources are checked every run.
    direct = scan_employers(companies_payload)
    for raw in direct:
        add(raw)

    # Broad discovery uses mechanical/engineering-specific searches instead of
    # generic "intern" searches. Four calls every 30 minutes = 192 calls/day,
    # leaving headroom under Adzuna's common free-tier daily allowance.
    broad_available = bool(APP_ID and APP_KEY)
    if broad_available:
        for query in (
            "Summer 2027 mechanical engineering intern",
            "Summer 2027 manufacturing engineering intern",
            "Summer 2027 process engineering intern",
            "Summer 2027 engineering co-op"
        ):
            try:
                for item in adzuna_search(query):
                    add(convert_adzuna(item))
            except Exception as e:
                print("adzuna warning", query, e)
    else:
        print("No Adzuna credentials configured; direct employer scanning is active, broad aggregator search is not.")

    # Give postings a grace period if a broad source was available but missed a
    # listing temporarily. Without a broad API configured, never delete the seed set.
    for key, old in old_by_key.items():
        if key in collected:
            continue
        # Purge previously embedded listings that no longer pass the stricter
        # mechanical-engineering and Summer 2027 filters.
        if not relevant(old.get("title", ""), old.get("summary", "")):
            continue
        if not is_summer_2027(old.get("title", ""), old.get("summary", "") + " " + old.get("term", "")):
            continue
        if not broad_available:
            keep = True
        else:
            last_seen = parse_iso(old.get("last_seen")) or parse_iso(old_payload.get("updated_at")) or now
            keep = (now - last_seen) <= timedelta(days=7)
        if keep:
            preserved = dict(old)
            preserved["first_seen"] = old.get("first_seen") or old_payload.get("updated_at") or now.isoformat()
            preserved["last_seen"] = old.get("last_seen") or old_payload.get("updated_at") or now.isoformat()
            preserved["_rank"] = 0
            collected[key] = preserved

    jobs = list(collected.values())
    for j in jobs:
        j.pop("_rank", None)
    jobs.sort(key=lambda j: (
        not j.get("is_new", False),
        j.get("company", "").lower(),
        j.get("title", "").lower()
    ))

    payload = {
        "updated_at": now.isoformat(),
        "source_note": (
            "Automatically refreshed from direct employer career pages/public ATS feeds"
            + (" plus Adzuna broad discovery." if broad_available else ". Add Adzuna credentials for broader discovery.")
        ),
        "jobs": jobs
    }
    new_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    pattern = r"const EMBEDDED_JOBS=.*?;\nconst EMBEDDED_COMPANIES="
    replacement = "const EMBEDDED_JOBS=" + new_json + ";\nconst EMBEDDED_COMPANIES="
    updated, n = re.subn(pattern, replacement, source_text, count=1, flags=re.S)
    if n != 1:
        raise SystemExit("Could not find embedded jobs block in index.html")
    INDEX.write_text(updated, encoding="utf-8")
    print(f"Embedded {len(jobs)} jobs: {len(direct)} direct-source candidates; broad_source={broad_available}")

if __name__ == "__main__":
    main()
