"""We Work Remotely scraper - the deliberately slow, polite one.

Unlike the other three sources this is HTML scraping, not an API, so it:
  * reads robots.txt in code and refuses any path it disallows,
  * identifies itself with a descriptive User-Agent (set JOBMARKET_CONTACT to add contact details),
  * runs strictly sequentially with a 1-2 s randomised pause between requests,
  * caches every page: a job page already stored on any earlier day is never fetched again.

    python -m collectors.wwr_scraper              # all categories
    python -m collectors.wwr_scraper --max-jobs 5 # smoke test
"""
from __future__ import annotations

import argparse
import asyncio
import random
import re
import time
from urllib import robotparser

import httpx
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from .common import RAW, USER_AGENT, atomic_write, fetch, get_logger, raw_dir, write_manifest

BASE = "https://weworkremotely.com"
CATEGORIES = [
    "remote-full-stack-programming-jobs",
    "remote-back-end-programming-jobs",
    "remote-front-end-programming-jobs",
    "remote-devops-sysadmin-jobs",
    "remote-design-jobs",
    "remote-product-jobs",
    "remote-customer-support-jobs",
    "remote-sales-and-marketing-jobs",
    "remote-management-and-finance-jobs",
    "all-other-remote-jobs",
]
JOB_HREF = re.compile(r"^/remote-jobs/[a-z0-9][a-z0-9\-]+$")
SKIP = {"/remote-jobs/new", "/remote-jobs/search", "/remote-jobs/find-your-plan"}

log = get_logger("wwr")


def slug(path: str) -> str:
    return re.sub(r"[^a-z0-9\-]", "_", path.strip("/").split("/")[-1])[:150]


def cached(name: str) -> bool:
    return any((RAW / "wwr").glob(f"*/{name}"))


async def main(max_jobs: int | None, min_delay: float, max_delay: float) -> None:
    started = time.time()
    out = raw_dir("wwr")
    stats = {"requests": 0, "categories": 0, "jobs_listed": 0, "jobs_fetched": 0,
             "jobs_cached": 0, "blocked_by_robots": 0, "errors": 0, "bytes": 0}

    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=60,
                                 follow_redirects=True) as client:
        # --- robots.txt -------------------------------------------------------
        r = await fetch(client, f"{BASE}/robots.txt")
        stats["requests"] += 1
        atomic_write(out / "robots.txt", r.content)
        rp = robotparser.RobotFileParser()
        rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        crawl_delay = rp.crawl_delay(USER_AGENT) or 0
        min_delay, max_delay = max(min_delay, crawl_delay), max(max_delay, crawl_delay)

        async def polite_get(path: str) -> httpx.Response | None:
            if not rp.can_fetch(USER_AGENT, f"{BASE}{path}"):
                stats["blocked_by_robots"] += 1
                log.warning("robots.txt disallows %s - skipped", path)
                return None
            await asyncio.sleep(random.uniform(min_delay, max_delay))
            try:
                resp = await fetch(client, f"{BASE}{path}", retries=3)
            except RuntimeError as e:
                stats["errors"] += 1
                log.error("%r", e)
                return None
            stats["requests"] += 1
            if resp.status_code != 200:
                stats["errors"] += 1
                log.error("HTTP %s for %s", resp.status_code, path)
                return None
            stats["bytes"] += len(resp.content)
            return resp

        # --- category pages: always refetched, they are the daily snapshot ---
        job_paths: dict[str, None] = {}
        for cat in CATEGORIES:
            resp = await polite_get(f"/categories/{cat}")
            if resp is None:
                continue
            atomic_write(out / f"category_{cat}.html", resp.content)
            stats["categories"] += 1
            for a in HTMLParser(resp.text).css("a[href]"):
                href = (a.attributes.get("href") or "").split("?")[0]
                if JOB_HREF.match(href) and href not in SKIP:
                    job_paths[href] = None
            log.info("category %-40s -> %d job links so far", cat, len(job_paths))
        stats["jobs_listed"] = len(job_paths)

        # --- job pages: fetched once, then served from the cache forever ------
        for path in job_paths:
            name = f"job_{slug(path)}.html"
            if cached(name):
                stats["jobs_cached"] += 1
                continue
            if max_jobs is not None and stats["jobs_fetched"] >= max_jobs:
                break
            resp = await polite_get(path)
            if resp is None:
                continue
            atomic_write(out / name, resp.content)
            stats["jobs_fetched"] += 1
            if stats["jobs_fetched"] % 25 == 0:
                log.info("fetched %d job pages", stats["jobs_fetched"])

    write_manifest("wwr", stats, started)
    log.info("done: %s", stats)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-jobs", type=int)
    ap.add_argument("--min-delay", type=float, default=1.0)
    ap.add_argument("--max-delay", type=float, default=2.0)
    a = ap.parse_args()
    asyncio.run(main(a.max_jobs, a.min_delay, a.max_delay))
