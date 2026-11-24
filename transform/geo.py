"""Tiny gazetteer: enough to tag the common tech hubs with a country. Not a geocoder."""
from __future__ import annotations

import re

COUNTRIES = {
    "US": ["united states", "usa", "u.s.", "u.s.a", "us"],
    "GB": ["united kingdom", "uk", "england", "scotland", "wales", "great britain"],
    "DE": ["germany", "deutschland"], "FR": ["france"], "NL": ["netherlands", "holland"],
    "CA": ["canada"], "AU": ["australia"], "IN": ["india"], "IE": ["ireland"], "ES": ["spain"],
    "PT": ["portugal"], "IT": ["italy"], "CH": ["switzerland"], "SE": ["sweden"], "NO": ["norway"],
    "DK": ["denmark"], "FI": ["finland"], "PL": ["poland"], "AT": ["austria"], "BE": ["belgium"],
    "IL": ["israel"], "SG": ["singapore"], "JP": ["japan"], "CN": ["china"], "BR": ["brazil"],
    "MX": ["mexico"], "AR": ["argentina"], "NZ": ["new zealand"], "CZ": ["czech republic", "czechia"],
    "EE": ["estonia"], "RO": ["romania"], "UA": ["ukraine"], "TR": ["turkey"], "KR": ["south korea"],
    "ZA": ["south africa"], "AE": ["uae", "united arab emirates"], "HK": ["hong kong"],
    "CO": ["colombia"], "GR": ["greece"], "HU": ["hungary"], "LT": ["lithuania"], "TW": ["taiwan"],
}
CITIES = {
    "US": ["san francisco", "sf", "bay area", "silicon valley", "new york", "nyc", "ny", "brooklyn", "manhattan",
           "seattle", "boston", "cambridge, ma", "austin", "los angeles", "la", "chicago", "denver", "boulder",
           "portland", "atlanta", "washington", "dc", "d.c.", "palo alto", "mountain view", "menlo park",
           "sunnyvale", "san mateo", "redwood city", "san jose", "oakland", "berkeley", "santa monica",
           "san diego", "miami", "dallas", "houston", "philadelphia", "pittsburgh", "raleigh", "durham",
           "salt lake city", "minneapolis", "detroit", "ann arbor", "nashville", "phoenix", "santa clara",
           "cupertino", "irvine", "santa barbara", "madison", "columbus", "st. louis", "baltimore"],
    "GB": ["london", "manchester", "edinburgh", "cambridge, uk", "oxford", "bristol", "glasgow", "leeds"],
    "DE": ["berlin", "munich", "münchen", "hamburg", "frankfurt", "cologne", "köln", "stuttgart", "düsseldorf",
           "dusseldorf", "leipzig", "dresden", "hannover", "nürnberg", "nuremberg", "bremen", "karlsruhe",
           "dortmund", "essen", "bonn", "mannheim", "heidelberg", "potsdam"],
    "FR": ["paris", "lyon", "toulouse"], "NL": ["amsterdam", "rotterdam", "utrecht", "eindhoven", "the hague"],
    "CA": ["toronto", "vancouver", "montreal", "montréal", "ottawa", "waterloo", "calgary"],
    "AU": ["sydney", "melbourne", "brisbane"], "IN": ["bangalore", "bengaluru", "mumbai", "delhi", "hyderabad", "pune", "chennai", "gurgaon"],
    "IE": ["dublin"], "ES": ["barcelona", "madrid", "valencia"], "PT": ["lisbon", "porto"],
    "CH": ["zurich", "zürich", "geneva", "lausanne", "basel"], "SE": ["stockholm", "gothenburg", "malmö"],
    "NO": ["oslo"], "DK": ["copenhagen"], "FI": ["helsinki"], "PL": ["warsaw", "krakow", "kraków", "wroclaw"],
    "AT": ["vienna", "wien"], "BE": ["brussels", "ghent"], "IL": ["tel aviv", "tel-aviv"], "JP": ["tokyo"],
    "CN": ["beijing", "shanghai", "shenzhen"], "BR": ["são paulo", "sao paulo"], "MX": ["mexico city"],
    "AR": ["buenos aires"], "CZ": ["prague"], "EE": ["tallinn"], "RO": ["bucharest"], "UA": ["kyiv", "kiev"],
    "TR": ["istanbul"], "KR": ["seoul"], "ZA": ["cape town"], "AE": ["dubai"], "IT": ["milan", "rome"],
    "HU": ["budapest"], "GR": ["athens"], "LT": ["vilnius"], "NZ": ["auckland", "wellington"], "TW": ["taipei"],
}
US_STATES = ("AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|"
             "NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC")
STATE_RE = re.compile(rf",\s?(?:{US_STATES})\b")
REGION_RE = re.compile(r"(?i)\b(europe|emea|eu|apac|latam|north america|worldwide|global|americas|asia)\b")

_lookup: dict[str, str] = {}
for _cc, _names in list(COUNTRIES.items()) + list(CITIES.items()):
    for _n in _names:
        _lookup.setdefault(_n, _cc)
# short/ambiguous tokens must match case-sensitively as upper-case words
_CASED = {"us": "US", "sf": "SF","ny": "NY", "la": "LA", "dc": "DC", "uk": "UK", "usa": "USA", "uae": "UAE", "nyc": "NYC"}
_plain = sorted((k for k in _lookup if k not in _CASED), key=len, reverse=True)
_PLAIN_RE = re.compile(r"(?i)(?<![A-Za-z])(" + "|".join(map(re.escape, _plain)) + r")(?![A-Za-z])")
_CASED_RE = re.compile(r"(?<![A-Za-z])(" + "|".join(_CASED.values()) + r")(?![A-Za-z])")


def guess_country(text: str) -> str | None:
    """ISO-2 country for the first recognisable place name, else None."""
    if not text:
        return None
    hits = [(m.start(), _lookup[m.group(1).lower()]) for m in _PLAIN_RE.finditer(text)]
    hits += [(m.start(), _lookup[m.group(1).lower()]) for m in _CASED_RE.finditer(text)]
    m = STATE_RE.search(text)
    if m:
        hits.append((m.start(), "US"))
    return min(hits)[1] if hits else None


def looks_like_location(text: str) -> bool:
    return bool(guess_country(text) or REGION_RE.search(text))
