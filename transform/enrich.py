"""Enrichment: skills, role family, seniority, salary -> annual USD."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent

# --------------------------------------------------------------------------- skills
_L, _R = r"(?<![A-Za-z0-9_])", r"(?![A-Za-z0-9_+#])"


class SkillMatcher:
    """Three passes: one big case-insensitive alternation, one case-sensitive, a few custom regexes."""

    def __init__(self, path: Path = HERE / "skills.yaml"):
        self.skills = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.category = {s["name"]: s["cat"] for s in self.skills}
        ci, cs, self.custom = {}, {}, []
        for s in self.skills:
            if "pattern" in s:
                self.custom.append((s["name"], re.compile(s["pattern"])))
            for a in s.get("aliases", []):
                (cs if s.get("cs") else ci)[a if s.get("cs") else a.lower()] = s["name"]
        self.ci_map, self.cs_map = ci, cs
        alt = lambda keys: "|".join(re.escape(k) for k in sorted(keys, key=len, reverse=True))  # longest first
        self.ci_re = re.compile(_L + "(" + alt(ci) + ")" + _R, re.I)
        self.cs_re = re.compile(_L + "(" + alt(cs) + ")" + _R)

    def find(self, text: str) -> set[str]:
        found = {self.ci_map[m.lower()] for m in self.ci_re.findall(text)}
        found |= {self.cs_map[m] for m in self.cs_re.findall(text)}
        found |= {name for name, rx in self.custom if rx.search(text)}
        return found


# --------------------------------------------------------------------------- role family / seniority
ROLE_RULES = [  # first match wins, so order = priority
    ("ML Engineer", r"machine learning|\bml\b|\bmle\b|\bai\b|deep learning|computer vision|\bnlp\b|\bllm|research engineer|applied scientist|mlops"),
    ("Data Scientist", r"data scien|research scientist|statistician|quantitative (?:research|analyst)|\bquant\b"),
    ("Data Engineer", r"data engineer|analytics engineer|\betl\b|data platform|data infrastructure|data architect|database (?:engineer|admin)"),
    ("Data Analyst", r"data analyst|business analyst|\bbi\b|business intelligence|analytics|\banalyst\b"),
    ("Engineering Manager", r"engineering manager|head of engineering|vp,? (?:of )?engineering|\bcto\b|director of engineering|engineering lead|tech(?:nical)? lead|team lead"),
    ("DevOps / Infrastructure", r"devops|\bsre\b|site reliability|infrastructure|platform engineer|cloud engineer|sysadmin|systems? administrator|security engineer|network engineer"),
    ("Software Engineer", r"software|developer|entwickler|engineer|full[- ]?stack|front[- ]?end|back[- ]?end|programmer|\bswe\b|\bios\b|android|mobile|hacker|architect|\bqa\b|firmware|embedded"),
    ("Product", r"product manager|product owner|product lead|head of product|\bpm\b|product management"),
    ("Design", r"design|\bux\b|\bui\b|illustrator|creative director"),
    ("Sales & Marketing", r"sales|marketing|account executive|account manager|growth|\bseo\b|business development|vertrieb|content|copywriter|social media"),
    ("Customer Support", r"support|customer success|customer service|kundenservice|kundenberater"),
]
ROLE_RULES = [(n, re.compile(p, re.I)) for n, p in ROLE_RULES]

SENIORITY_RULES = [
    ("intern", r"\bintern(?:ship)?s?\b|praktik|werkstudent|working student|\bco-?op\b"),
    ("staff+", r"\bstaff\b|\bprincipal\b|distinguished|\bfellow\b"),
    ("lead/manager", r"\blead\b|\bmanager\b|\bhead of\b|\bdirector\b|\bvp\b|\bchief\b|\bcto\b|leiter|teamleit"),
    ("senior", r"\bsenior\b|\bsr\.?\b|experienced"),
    ("junior", r"\bjunior\b|\bjr\.?\b|entry[- ]level|\bgraduate\b|new grad|trainee|associate|azubi|ausbildung"),
]
SENIORITY_RULES = [(n, re.compile(p, re.I)) for n, p in SENIORITY_RULES]


def role_family(title: str, fallback: str = "") -> str:
    for text in (title, fallback):
        for name, rx in ROLE_RULES:
            if text and rx.search(text):
                return name
    return "Other"


def seniority(title: str) -> str:
    for name, rx in SENIORITY_RULES:
        if rx.search(title or ""):
            return name
    return "unspecified"


# --------------------------------------------------------------------------- salary
FX_TO_USD = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "CAD": 0.73, "AUD": 0.66, "CHF": 1.13,
             "SGD": 0.74, "INR": 0.012, "SEK": 0.095, "PLN": 0.25}   # fixed table, see README
SYMBOL = {"$": "USD", "€": "EUR", "£": "GBP"}
PERIOD_MULT = {"year": 1, "month": 12, "week": 52, "day": 230, "hour": 2080}
_NUM = r"\d{1,3}(?:[.,]\d{3})+|\d+(?:\.\d+)?"
_CODE = r"USD|EUR|GBP|CAD|AUD|CHF|SGD"
RANGE_RE = re.compile(
    rf"(?P<code0>{_CODE})?\s?(?P<c1>[$€£])?\s?(?P<a>{_NUM})\s?(?P<k1>[kK])?\s?(?:-|–|—|to)\s?"
    rf"(?:US|CA|AU)?(?P<c2>[$€£])?\s?(?P<b>{_NUM})\s?(?P<k2>[kK])?(?![\dMmBb])\s?(?P<code>{_CODE})?")
SINGLE_RE = re.compile(
    rf"(?P<c1>[$€£])\s?(?P<a>{_NUM})\s?(?P<k1>[kK])?(?![\dMmBb,.]\d|[MmBb]\b|\s?(?:million|billion|mm\b))\+?\s?(?P<code>{_CODE})?")
PERIOD_RE = re.compile(r"(?i)^\s?(?:/|per\s|an?\s|p\.?)\s?(hour|hr|h\b|day|week|month|mo\b|year|yr|annum|a\b)|^\s?(hourly|daily|monthly|annually)")
_PERIOD_KEY = {"hour": "hour", "hr": "hour", "h": "hour", "hourly": "hour", "day": "day", "daily": "day",
               "week": "week", "month": "month", "mo": "month", "monthly": "month"}
BAD_CONTEXT_RE = re.compile(r"(?i)(raised|funding|series [a-e]|revenue|arr\b|valuation|seed|backed|grant|bonus|budget|customers|users|employees|people)\W*$")


def _num(s: str, k: str | None) -> float:
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", s):
        v = float(re.sub(r"[.,]", "", s))
    else:
        v = float(s)
    return v * 1000 if k else v


def _finish(lo: float, hi: float, cur: str, tail: str):
    m = PERIOD_RE.search(tail)
    period = _PERIOD_KEY.get((m.group(1) or m.group(2)).lower(), "year") if m else "year"
    if period == "year" and hi < 1000:      # "$120-150" with no k and no period: can't be trusted
        return None
    usd_lo, usd_hi = (v * PERIOD_MULT[period] * FX_TO_USD[cur] for v in (lo, hi))
    if not (20_000 <= usd_lo <= usd_hi <= 900_000) or usd_hi > 4 * usd_lo:
        return None                          # drop values that don't make sense
    return {"salary_min": lo, "salary_max": hi, "currency": cur, "salary_period": period,
            "salary_usd_min": round(usd_lo), "salary_usd_max": round(usd_hi)}


def parse_salary(text: str, allow_single: bool = True):
    """First plausible salary in `text` as a dict, or None.

    Handles $120k-150k, $120,000 - $150,000, €60.000, 80-100k EUR, $50/hr, £500 per day.
    """
    for m in RANGE_RE.finditer(text):
        sym = m.group("c1") or m.group("c2")
        code = m.group("code") or m.group("code0")
        k1, k2 = m.group("k1"), m.group("k2")
        if not (sym or code or (k1 and k2)):      # "2-5 years", "10-50 people" never qualify
            continue
        if BAD_CONTEXT_RE.search(text[max(0, m.start() - 25):m.start()]):
            continue
        lo, hi = _num(m.group("a"), k1 or (k2 if float(re.sub(r"[.,]", "", m.group("a"))) < 1000 else None)), _num(m.group("b"), k2)
        cur = code or SYMBOL.get(sym or "$", "USD")
        if sym == "$" and code in ("CAD", "AUD", "SGD"):
            cur = code
        res = _finish(lo, hi, cur, text[m.end():m.end() + 14])
        if res:
            return res
    if allow_single:
        for m in SINGLE_RE.finditer(text):
            if BAD_CONTEXT_RE.search(text[max(0, m.start() - 25):m.start()]):
                continue
            v = _num(m.group("a"), m.group("k1"))
            code = m.group("code")
            cur = code if code and m.group("c1") == "$" else SYMBOL[m.group("c1")]
            res = _finish(v, v, cur, text[m.end():m.end() + 14])
            if res:
                return res
    return None


def structured_salary(row: dict):
    """Salary that arrived as fields (RemoteOK, WWR) -> same dict shape, with sanity checks."""
    lo, hi = row.get("salary_min"), row.get("salary_max")
    cur, period = row.get("currency") or "USD", row.get("salary_period") or "year"
    if not lo or cur not in FX_TO_USD or period not in PERIOD_MULT:
        return None
    hi = hi or lo
    usd_lo, usd_hi = (v * PERIOD_MULT[period] * FX_TO_USD[cur] for v in (lo, hi))
    if not (20_000 <= usd_lo <= usd_hi <= 900_000) or usd_hi > 4 * usd_lo:
        return None
    return {"salary_usd_min": round(usd_lo), "salary_usd_max": round(usd_hi)}


def enrich(jobs: list[dict]) -> list[dict]:
    """Adds role_family, seniority, salary_usd_*; returns job_skills rows."""
    sm = SkillMatcher()
    job_skills = []
    for j in jobs:
        desc = j["description"]
        header = desc.split("\n", 1)[0] if j["source"] == "hn" else ""
        j["role_family"] = role_family(j["title"], header[:300])
        j["seniority"] = seniority(j["title"])
        sal = structured_salary(j)
        if sal is None:
            j["salary_min"] = j["salary_max"] = j["currency"] = j["salary_period"] = None
            # headline first (most reliable), then ranges anywhere in the body
            sal = (parse_salary(header) if header else None) or parse_salary(desc, allow_single=False)
        j["salary_usd_min"] = j["salary_usd_max"] = None
        if sal:
            j.update(sal)
        for s in sm.find(j["title"] + "\n" + desc):
            job_skills.append({"job_id": j["job_id"], "skill": s, "category": sm.category[s]})
    return job_skills
