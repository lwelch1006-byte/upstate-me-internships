#!/usr/bin/env python3
import json, os, re
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
APP_ID = os.getenv("ADZUNA_APP_ID", "")
APP_KEY = os.getenv("ADZUNA_APP_KEY", "")

LOCATIONS = ["Greenville, SC", "Spartanburg, SC", "Anderson, SC"]
QUERIES = [
    "mechanical engineering intern",
    "manufacturing engineering intern",
    "process engineering intern",
    "quality engineering intern",
    "mechanical design intern",
    "product engineering intern",
    "test validation engineering intern",
    "reliability engineering intern",
    "automation controls engineering intern",
    "project engineering intern",
    "thermal engineering intern",
]

LARGE = {
    "ge vernova","michelin","bmw","bmw group","jacobs","vertiv","milliken",
    "zf","opmobility","op mobility","illinois tool works","itw","hubbell",
    "bosch","lockheed martin","fluor","magna","afl","duke energy","eaton","borgwarner","jtekt"
}
SMALL = {
    "air compressor services","acs","ktm solutions","schot engineers","h2l",
    "tfs engineers","peritus engineers","engineering design services","dwg",
    "eliant engineering","devita"
}

def search(what, where):
    params = {
        "app_id": APP_ID, "app_key": APP_KEY, "what": what, "where": where,
        "distance": 50, "results_per_page": 50, "content-type": "application/json",
    }
    url = "https://api.adzuna.com/v1/api/jobs/us/search/1?" + urlencode(params)
    req = Request(url, headers={"User-Agent":"UpstateMEInternships/1.0"})
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode()).get("results", [])

def classify_type(title, desc):
    t=(title+" "+desc).lower()
    rules=[
      ("Manufacturing",["manufacturing","industrialization","technical planning"]),
      ("Quality",["quality","supplier quality","dimensional"]),
      ("Process",["process engineering","process engineer"]),
      ("Automation",["automation","controls","robotics","mechatronics"]),
      ("Reliability",["reliability","sustaining","maintenance engineering"]),
      ("Test",["test","validation","verification"]),
      ("R&D",["r&d","research and development","research & development"]),
      ("Design",["design","product engineering","product development"]),
      ("Mechanical",["mechanical","thermal","hvac"]),
      ("Project",["project","engineering intern"]),
    ]
    for label, words in rules:
        if any(w in t for w in words): return label
    return "Project"

def classify_size(company):
    c=re.sub(r"[^a-z0-9 &]+","",company.lower()).strip()
    if any(x in c for x in SMALL): return "small"
    if any(x in c for x in LARGE): return "large"
    return "other"

def relevant(title, desc):
    t=(title+" "+desc).lower()
    return any(x in t for x in ["intern","co-op","coop","student"]) and any(x in t for x in [
      "mechanical","manufacturing","process","quality","design","product","test",
      "validation","reliability","engineering","automation","controls","project","thermal"
    ])

def summary(desc):
    s=re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",desc or "")).strip()
    return s if len(s)<=180 else s[:177].rsplit(" ",1)[0]+"…"

def main():
    if not APP_ID or not APP_KEY:
        print("No Adzuna credentials configured; keeping current embedded listings.")
        return

    raw=[]
    for loc in LOCATIONS:
        for q in QUERIES:
            try: raw.extend(search(q,loc))
            except Exception as e: print("warning",q,loc,e)

    now=datetime.now(timezone.utc)
    seen=set(); jobs=[]
    for item in raw:
        title=item.get("title") or ""
        desc=item.get("description") or ""
        if not relevant(title,desc): continue
        company=(item.get("company") or {}).get("display_name") or "Unknown employer"
        location=(item.get("location") or {}).get("display_name") or "Upstate SC"
        url=item.get("redirect_url") or ""
        fid=str(item.get("id") or url or f"{company}|{title}|{location}")
        if fid in seen: continue
        seen.add(fid)
        created=item.get("created") or ""
        is_new=False
        if created:
            try:
                dt=datetime.fromisoformat(created.replace("Z","+00:00"))
                is_new=(now-dt.astimezone(timezone.utc)).days<=7
            except ValueError: pass
        salary=""
        if item.get("salary_min") and item.get("salary_max"):
            salary=f"${item['salary_min']:,.0f}–${item['salary_max']:,.0f}"
        jobs.append({
          "id":fid,"company":company,"title":re.sub(r"<[^>]+>","",title),
          "location":location,"type":classify_type(title,desc),
          "company_size":classify_size(company),"term":"Current","salary":salary,
          "summary":summary(desc),"apply_url":url,"is_new":is_new
        })

    jobs.sort(key=lambda j:(not j["is_new"],j["company"].lower(),j["title"].lower()))
    payload={
      "updated_at":datetime.now(timezone.utc).isoformat(),
      "source_note":"Automatically refreshed from the Adzuna Jobs API.",
      "jobs":jobs
    }

    text=INDEX.read_text(encoding="utf-8")
    new_json=json.dumps(payload,separators=(",",":"),ensure_ascii=False).replace("</","<\\/")
    pattern=r"const EMBEDDED_JOBS=.*?;\nconst EMBEDDED_COMPANIES="
    replacement="const EMBEDDED_JOBS="+new_json+";\nconst EMBEDDED_COMPANIES="
    updated,n=re.subn(pattern,replacement,text,count=1,flags=re.S)
    if n!=1:
        raise SystemExit("Could not find embedded jobs block in index.html")
    INDEX.write_text(updated,encoding="utf-8")
    print(f"Embedded {len(jobs)} jobs in index.html")

if __name__=="__main__":
    main()
