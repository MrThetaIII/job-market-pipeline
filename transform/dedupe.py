"""Cross-board duplicate detection.

The same opening is often posted on several boards. Two listings are treated as one job when
    * they come from different sources,
    * they were posted within 30 days of each other,
    * company names match   (rapidfuzz token_set_ratio >= 90 after normalisation), and
    * titles match          (rapidfuzz token_sort_ratio >= 85 after normalisation).

Candidates are blocked on the first 4 letters of the normalised company so we never compare
all pairs. Matches are merged with union-find; the earliest posting in a group is canonical.

HN posts are deliberately NOT deduped against other HN posts: a company that reposts every month
is a fresh monthly observation, which is exactly what the trend analysis counts.
"""
from __future__ import annotations

import re
from collections import defaultdict

from rapidfuzz import fuzz

WINDOW_DAYS = 30
_SUFFIX = re.compile(r"\b(inc|llc|ltd|gmbh|ag|se|co|corp|corporation|company|limited|sa|bv|plc|ug|kg|group|labs?|technologies|technology|hq|io|ai)\b")
_TITLE_NOISE = re.compile(r"\((?:m/w/d|f/m/d|w/m/d|m/f/d|all genders|remote|[^)]{0,25})\)|\b(remote|m/w/d|f/m/x|w/m/d|all genders)\b")


def norm_company(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    return re.sub(r"\s+", " ", _SUFFIX.sub(" ", s)).strip()


def norm_title(s: str) -> str:
    s = _TITLE_NOISE.sub(" ", (s or "").lower())
    s = re.sub(r"\bsr\b\.?", "senior", s)
    s = re.sub(r"\bjr\b\.?", "junior", s)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#/ ]", " ", s)).strip()


def dedupe(jobs: list[dict]) -> list[dict]:
    """Adds dup_group_id / is_canonical to every job; returns the matched pairs."""
    blocks: dict[str, list[int]] = defaultdict(list)
    nc, nt = [], []
    for i, j in enumerate(jobs):
        nc.append(norm_company(j["company"]))
        nt.append(norm_title(j["title"]))
        if len(nc[i]) >= 2:
            blocks[nc[i][:4]].append(i)

    parent = list(range(len(jobs)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    pairs = []
    for idxs in blocks.values():
        if len({jobs[i]["source"] for i in idxs}) < 2:
            continue
        idxs.sort(key=lambda i: jobs[i]["posted_at"])
        for a_pos, a in enumerate(idxs):
            for b in idxs[a_pos + 1:]:
                if (jobs[b]["posted_at"] - jobs[a]["posted_at"]).days > WINDOW_DAYS:
                    break
                if jobs[a]["source"] == jobs[b]["source"]:
                    continue
                cs = fuzz.token_set_ratio(nc[a], nc[b])
                if cs < 90:
                    continue
                # token_sort (not token_set): "Account Executive" must not match every
                # longer title that merely contains those two words
                ts = fuzz.token_sort_ratio(nt[a], nt[b])
                if ts < 85:
                    continue
                parent[find(b)] = find(a)
                pairs.append({"job_id_a": jobs[a]["job_id"], "job_id_b": jobs[b]["job_id"],
                              "source_a": jobs[a]["source"], "source_b": jobs[b]["source"],
                              "company_score": cs, "title_score": ts})

    first_of_group: dict[int, int] = {}
    for i in sorted(range(len(jobs)), key=lambda i: jobs[i]["posted_at"]):
        root = find(i)
        first_of_group.setdefault(root, i)
        jobs[i]["dup_group_id"] = jobs[first_of_group[root]]["job_id"]
        jobs[i]["is_canonical"] = first_of_group[root] == i
    return pairs
