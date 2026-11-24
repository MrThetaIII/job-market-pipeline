"""Map every raw source into one `jobs` schema, validate with Pydantic, collect rejects.

Reads only data/raw/ - never the network - so it can be rerun at any time.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from .geo import guess_country, looks_like_location

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"


# --------------------------------------------------------------------------- schema
class Job(BaseModel):
    job_id: str
    source: Literal["hn", "remoteok", "arbeitnow", "wwr"]
    url: str = Field(pattern=r"^https?://")
    title: str = Field(min_length=2, max_length=160)
    company: str = Field(min_length=1, max_length=100)
    location_raw: Optional[str] = None
    country: Optional[str] = None
    is_remote: Optional[bool] = None
    employment_type: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    currency: Optional[str] = None
    salary_period: Optional[str] = None
    description: str = Field(min_length=40)
    posted_at: datetime
    first_seen: date
    last_seen: date
    parse_method: Optional[str] = None  # HN only: pipe | alt_sep | regex

    @field_validator("posted_at")
    @classmethod
    def sane_date(cls, v: datetime) -> datetime:
        if v.year < 2010 or v > datetime.now(timezone.utc) + timedelta(days=2):
            raise ValueError("posted_at outside 2010..now")
        return v

    @model_validator(mode="after")
    def consistent(self) -> "Job":
        if self.salary_min and self.salary_max and self.salary_min > self.salary_max:
            raise ValueError("salary_min > salary_max")
        if self.last_seen < self.first_seen:
            raise ValueError("last_seen before first_seen")
        return self


def make_id(source: str, source_id: str | int) -> str:
    return hashlib.sha1(f"{source}:{source_id}".encode()).hexdigest()[:16]


def html_to_text(s: str) -> str:
    s = re.sub(r"(?i)<(?:p|br|li|/h\d|/div|/tr)\b[^>]*>", "\n", s or "")
    s = re.sub(r'(?is)<a\s[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
               lambda m: m.group(1) if m.group(2).strip().startswith("http") else m.group(2), s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    s = re.sub(r"[ \t ​]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def snapshot_dirs(source: str) -> list[Path]:
    return sorted(p for p in (RAW / source).glob("*") if p.is_dir())


# --------------------------------------------------------------------------- HN parsing
ROLE_RE = re.compile(
    r"(?i)\b(engineers?|developers?|dev|scientists?|analysts?|designers?|managers?|architects?|"
    r"devops|sre|programmers?|researchers?|director|intern(?:ship)?s?|full[- ]?stack|front[- ]?end|"
    r"back[- ]?end|swe|hackers?|sysadmin|administrator|recruiter|marketer|founder|cto|vp|head of|"
    r"lead|product|sales|support|qa|roles|positions|specialist|writer|consultant)\b")
REMOTE_RE = re.compile(r"(?i)\b(remote|wfh|work from home|distributed team|anywhere)\b")
NOT_REMOTE_RE = re.compile(r"(?i)\b(no remote|not remote|non-remote|remote not|no-remote|onsite only|on-site only)\b")
ONSITE_RE = re.compile(r"(?i)\b(on-?site|in-?office|in-?person|hybrid)\b")
EMPLOY_RE = re.compile(r"(?i)\b(full[- ]?time|part[- ]?time|contract(?:or)?|freelance|intern(?:ship)?s?|permanent|temporary)\b")
SALARY_HINT_RE = re.compile(r"[$€£]\s?\d|\b\d{2,3}\s?k\b", re.I)
URL_RE = re.compile(r"https?://\S+|\bwww\.\S+|\b[\w.-]+\.(?:com|io|ai|co|org|net|dev|app)/\S*", re.I)
STRONG_ROLE_RE = re.compile(r"(?i)\b(engineers?|developers?|scientists?|designers?|analysts?|programmers?)\b")
VISA_RE = re.compile(r"(?i)\bvisa\b|\bsponsor")
SEP_RE = re.compile(r"\s[-–—•·]\s|\s[-–—]{2,}\s")
TITLE_FALLBACK_RE = re.compile(
    r"(?i)\b((?:(?:senior|sr\.?|staff|principal|lead|junior|jr\.?|founding|head of|chief|vp of)[ \t]+)?"
    r"(?:[\w+.#&-]+[ \t]+){0,3}?(?:engineers?|developers?|scientists?|analysts?|designers?|"
    r"programmers?|architects?|managers?|hackers?|researchers?|interns?|cto|devops|sre))\b")
EMPLOY_MAP = {"full": "full_time", "part": "part_time", "cont": "contract", "free": "contract",
              "inte": "internship", "perm": "full_time", "temp": "contract"}


def _clean_company(s: str) -> str:
    s = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", s)                    # (YC S21), (https://...), [remote]
    s = URL_RE.sub("", s)
    s = re.sub(r"(?i)\s+(is|are)\s+(hiring|looking).*$", "", s)
    return s.strip(" -–—:|,.*(")


def _classify(seg: str) -> set[str]:
    kinds: set[str] = set()
    bare = seg.strip()
    if not bare:
        return {"empty"}
    if URL_RE.fullmatch(bare) or bare.lower().startswith(("http", "www.")):
        return {"url"}
    if REMOTE_RE.search(bare):
        kinds.add("remote")
    if ONSITE_RE.search(bare):
        kinds.add("onsite")
    if EMPLOY_RE.search(bare):
        kinds.add("employment")
    if SALARY_HINT_RE.search(bare):
        kinds.add("salary")
    if VISA_RE.search(bare):
        kinds.add("visa")
    if looks_like_location(bare):
        kinds.add("location")
    if "salary" in kinds:
        kinds.discard("location")            # "US$85k" is a salary, not a place
    elif ROLE_RE.search(EMPLOY_RE.sub("", bare)):
        kinds.add("title")
    return kinds or {"unknown"}


def parse_hn_header(text: str) -> dict:
    """Parse the first line of a 'Who is hiring?' post.

    Strategy 1 (pipe):    Company | Role | Location | REMOTE | $150k
    Strategy 2 (alt_sep): same idea, but ' - ' / ' – ' / ' • ' separators (common before ~2014)
    Strategy 3 (regex):   free text - pull company from the opening words, role from keywords
    """
    header = text.split("\n", 1)[0].strip()
    out = {"company": None, "title": None, "location_raw": None, "is_remote": None,
           "employment_type": None, "parse_method": None, "header": header[:400]}

    segs = [s.strip() for s in header.split("|")]
    method = "pipe"
    if len(segs) < 3:
        alt = [s.strip() for s in SEP_RE.split(header)]
        if len(alt) >= 3:
            segs, method = alt, "alt_sep"
        elif len(segs) < 2:
            segs, method = (alt, "alt_sep") if len(alt) == 2 else ([], "regex")

    if segs:
        # a trailing segment often runs straight into the prose - keep only its first clause
        segs = [s if len(s) <= 90 else "" for s in segs]
        kinds = [_classify(s) for s in segs]
        # company: pipe convention says first; alt_sep often leads with the location instead
        ci = 0
        if method == "alt_sep" or kinds[0] & {"empty", "url"}:
            unknown = [i for i, k in enumerate(kinds) if k == {"unknown"}]
            non_meta = [i for i, k in enumerate(kinds) if not k & {"empty", "url", "location", "remote", "employment", "salary", "visa", "onsite"}]
            ci = (unknown or non_meta or [0])[0]
        elif STRONG_ROLE_RE.search(segs[0]):   # "Senior Engineer | Acme | Remote": role came first
            unknown = [i for i, k in enumerate(kinds) if k == {"unknown"}]
            ci = unknown[0] if unknown else 0
        out["company"] = _clean_company(segs[ci]) or None
        titles, locs = [], []
        for i, (s, k) in enumerate(zip(segs, kinds)):
            if i == ci:
                continue
            if "title" in k:
                titles.append(re.sub(r"\s*\((?i:remote|onsite|hybrid)[^)]*\)", "", s).strip())
            elif "location" in k or (k & {"remote", "onsite"} and len(s) > 12):
                locs.append(s)
            if "employment" in k and not out["employment_type"]:
                out["employment_type"] = EMPLOY_MAP.get(EMPLOY_RE.search(s).group(1).lower()[:4])
        if titles:
            out["title"] = "; ".join(titles[:3])[:160]
        if locs:
            out["location_raw"] = "; ".join(locs)[:200]
        out["parse_method"] = method

    if not out["company"]:  # ---- strategy 3: regex on free text
        out["parse_method"] = "regex"
        m = re.match(r"^([A-Z0-9][\w&.'+!-]*(?:\s[A-Z0-9&][\w&.'+!-]*){0,3})\s*(?:\(|,|:|\bis\b|\bare\b|\bseeks?\b|-|–|—|/)", header)
        if m:
            out["company"] = _clean_company(m.group(1)) or None
    if not out["title"]:
        m = None
        for scope in (header, text[:1500]):
            m = m or TITLE_FALLBACK_RE.search(scope)
        if m:
            t = re.sub(r"(?i)^(?:is|are|for|a|an|the|our|hiring|seeking|looking|and|of|to|with|as|we|need|more|few|two|first)\s+", "", m.group(1).strip())
            out["title"] = t[:160]
            if out["parse_method"] in ("pipe", "alt_sep"):
                out["parse_method"] += "+regex_title"
        elif out["company"] and out["parse_method"] in ("pipe", "alt_sep"):
            # a well-formed header that names no role: almost always "we have several openings"
            out["title"] = "Multiple / unspecified roles"
            out["parse_method"] += "+no_title"

    blob = header + " " + (out["location_raw"] or "")
    if NOT_REMOTE_RE.search(header):
        out["is_remote"] = False
    elif REMOTE_RE.search(blob):
        out["is_remote"] = True
    elif ONSITE_RE.search(header) or out["location_raw"]:
        out["is_remote"] = False
    elif REMOTE_RE.search(text[:1500]):
        out["is_remote"] = True
    return out


def iter_hn() -> Iterator[tuple[dict, str | None]]:
    """Yield (row, early_reject_reason). Uses the newest stored copy of every thread."""
    latest: dict[str, Path] = {}
    for d in snapshot_dirs("hn"):
        for f in d.glob("thread_*.jsonl"):
            latest[f.name] = f
    for f in latest.values():
        snap = date.fromisoformat(f.parent.name)
        with f.open(encoding="utf-8") as fh:
            next(fh, None)  # line 1 is the thread itself
            for line in fh:
                try:
                    c = json.loads(line)
                except json.JSONDecodeError:
                    yield {"source": "hn", "source_id": None, "raw": line[:300]}, "invalid_json"
                    continue
                if not c:
                    continue
                base = {"source": "hn", "source_id": c.get("id"),
                        "url": f"https://news.ycombinator.com/item?id={c.get('id')}"}
                if c.get("deleted") or c.get("dead") or not c.get("text"):
                    yield base, "deleted_or_dead"
                    continue
                text = html_to_text(c["text"])
                p = parse_hn_header(text)
                posted = datetime.fromtimestamp(c["time"], tz=timezone.utc)
                yield {**base, "job_id": make_id("hn", c["id"]),
                       "title": p["title"], "company": p["company"],
                       "location_raw": p["location_raw"],
                       "country": guess_country(p["location_raw"] or ""),
                       "is_remote": p["is_remote"], "employment_type": p["employment_type"],
                       "description": text, "posted_at": posted,
                       "first_seen": posted.date(), "last_seen": max(snap, posted.date()),
                       "parse_method": p["parse_method"]}, None


# --------------------------------------------------------------------------- RemoteOK
def iter_remoteok() -> Iterator[tuple[dict, str | None]]:
    seen: dict[str, dict] = {}
    for d in snapshot_dirs("remoteok"):
        snap = date.fromisoformat(d.name)
        for f in sorted(d.glob("api_*.json")):
            for j in json.loads(f.read_text(encoding="utf-8"))[1:]:  # [0] = legal notice
                sid = str(j.get("id"))
                if sid in seen:
                    seen[sid]["last_seen"] = snap
                    continue
                smin, smax = j.get("salary_min") or None, j.get("salary_max") or None
                seen[sid] = {
                    "source": "remoteok", "source_id": sid, "job_id": make_id("remoteok", sid),
                    "url": j.get("url") or "", "title": (j.get("position") or "").strip(),
                    "company": (j.get("company") or "").strip(),
                    "location_raw": j.get("location") or None,
                    "country": guess_country(j.get("location") or ""), "is_remote": True,
                    "employment_type": None, "salary_min": smin, "salary_max": smax or smin,
                    "currency": "USD" if smin else None, "salary_period": "year" if smin else None,
                    "description": html_to_text(j.get("description") or "") + "\nTags: " + ", ".join(j.get("tags") or []),
                    "posted_at": j.get("date"), "first_seen": snap, "last_seen": snap}
    for row in seen.values():
        yield row, None


# --------------------------------------------------------------------------- Arbeitnow
def iter_arbeitnow() -> Iterator[tuple[dict, str | None]]:
    seen: dict[str, dict] = {}
    for d in snapshot_dirs("arbeitnow"):
        snap = date.fromisoformat(d.name)
        for f in sorted(d.glob("page_*.json")):
            for j in json.loads(f.read_text(encoding="utf-8")).get("data", []):
                sid = j.get("slug")
                if sid in seen:
                    seen[sid]["last_seen"] = snap
                    continue
                types = " ".join(j.get("job_types") or []).lower()
                emp = ("internship" if "prakti" in types or "intern" in types else
                       "part_time" if "teilzeit" in types or "part" in types else
                       "contract" if "befristet" in types.replace("unbefristet", "") or "contract" in types or "freelance" in types else
                       "full_time" if types else None)
                seen[sid] = {
                    "source": "arbeitnow", "source_id": sid, "job_id": make_id("arbeitnow", sid),
                    "url": j.get("url") or "", "title": (j.get("title") or "").strip(),
                    "company": (j.get("company_name") or "").strip(),
                    "location_raw": j.get("location") or None,
                    "country": guess_country(j.get("location") or "") or "DE",
                    "is_remote": bool(j.get("remote")), "employment_type": emp,
                    "description": html_to_text(j.get("description") or "") + "\nTags: " + ", ".join(j.get("tags") or []),
                    "posted_at": datetime.fromtimestamp(j["created_at"], tz=timezone.utc) if j.get("created_at") else None,
                    "first_seen": snap, "last_seen": snap}
    for row in seen.values():
        yield row, None


# --------------------------------------------------------------------------- We Work Remotely
LD_RE = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)
WWR_HREF = re.compile(r'href="/remote-jobs/([a-z0-9][a-z0-9\-]+)"')
WWR_EMP = {"FULL_TIME": "full_time", "PART_TIME": "part_time", "CONTRACTOR": "contract",
           "CONTRACT": "contract", "INTERN": "internship", "TEMPORARY": "contract"}


def iter_wwr() -> Iterator[tuple[dict, str | None]]:
    # category pages are the daily snapshot: they tell us on which days a job was still listed
    listed: dict[str, list[date]] = {}
    pages: dict[str, Path] = {}
    for d in snapshot_dirs("wwr"):
        snap = date.fromisoformat(d.name)
        for f in d.glob("category_*.html"):
            for slug in set(WWR_HREF.findall(f.read_text(encoding="utf-8", errors="replace"))):
                listed.setdefault(slug, []).append(snap)
        for f in d.glob("job_*.html"):
            pages.setdefault(f.stem[4:], f)
    for slug, f in pages.items():
        snap = date.fromisoformat(f.parent.name)
        days = listed.get(slug, []) + [snap]
        base = {"source": "wwr", "source_id": slug, "job_id": make_id("wwr", slug),
                "url": f"https://weworkremotely.com/remote-jobs/{slug}"}
        ld = None
        for block in LD_RE.findall(f.read_text(encoding="utf-8", errors="replace")):
            try:
                cand = json.loads(block, strict=False)
            except json.JSONDecodeError:
                continue
            if isinstance(cand, dict) and cand.get("@type") == "JobPosting":
                ld = cand
                break
        if ld is None:
            yield base, "no_jobposting_jsonld"
            continue
        org = ld.get("hiringOrganization") or {}
        sal = ld.get("baseSalary") or {}
        val = sal.get("value") if isinstance(sal, dict) else None
        smin = smax = period = None
        if isinstance(val, dict):
            smin, smax = val.get("minValue") or val.get("value"), val.get("maxValue") or val.get("value")
            period = {"YEAR": "year", "MONTH": "month", "HOUR": "hour", "DAY": "day", "WEEK": "week"}.get(str(val.get("unitText", "")).upper())
        try:
            smin, smax = (float(smin) if smin else None), (float(smax) if smax else None)
        except (TypeError, ValueError):
            smin = smax = None
        loc = ld.get("applicantLocationRequirements") or ld.get("jobLocation") or []
        loc = loc if isinstance(loc, list) else [loc]
        names = [(l.get("name") or (l.get("address") or {}).get("addressCountry") or "") if isinstance(l, dict) else str(l) for l in loc]
        names = [n for n in names if isinstance(n, str) and n]
        loc_raw = ", ".join(names[:8]) + (f" (+{len(names) - 8} more)" if len(names) > 8 else "") if names else None
        emp = ld.get("employmentType")
        emp = emp[0] if isinstance(emp, list) and emp else emp
        yield {**base, "title": html.unescape(ld.get("title") or "").strip(),
               "company": (org.get("name") or "").strip() if isinstance(org, dict) else "",
               "location_raw": loc_raw,
               "country": (names[0] if re.fullmatch(r"[A-Z]{2}", names[0]) else guess_country(names[0])) if len(names) == 1 else None,
               "is_remote": True, "employment_type": WWR_EMP.get(str(emp).upper()),
               "salary_min": smin, "salary_max": smax,
               "currency": (sal.get("currency") if isinstance(sal, dict) and smin else None),
               "salary_period": period if smin else None,
               "description": html_to_text(html.unescape(ld.get("description") or "")),
               "posted_at": str(ld.get("datePosted") or "").replace(" UTC", "+00:00") or None,
               "first_seen": min(days), "last_seen": max(days)}, None


# --------------------------------------------------------------------------- driver
def normalize() -> tuple[list[dict], list[dict]]:
    """Return (valid job rows, reject rows)."""
    jobs, rejects = [], []
    for it in (iter_hn(), iter_remoteok(), iter_arbeitnow(), iter_wwr()):
        for row, early in it:
            if early is None:
                # cheap, explicit pre-checks give more useful reasons than a generic schema error
                if not row.get("company"):
                    early = "no_company_found"
                elif not row.get("title"):
                    early = "no_title_found"
            if early is None:
                row["company"] = row["company"][:100]
                try:
                    sid = row.pop("source_id")
                    jobs.append(Job(**row).model_dump())
                    continue
                except ValidationError as e:
                    row["source_id"] = sid
                    err = e.errors()[0]
                    early = f"{'.'.join(map(str, err['loc'])) or 'row'}: {err['msg']}"[:120]
            rejects.append({"source": row["source"], "source_id": str(row.get("source_id")),
                            "url": row.get("url"), "reason": early,
                            "sample": (row.get("description") or row.get("raw") or "")[:200]})
    return jobs, rejects
