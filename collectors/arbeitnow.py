"""Arbeitnow collector: paginate /api/job-board-api until links.next is empty.

Pages are fetched a few at a time (default 3 concurrent) - enough to be quick,
low enough to stay polite on a free public API.

    python -m collectors.arbeitnow
"""
from __future__ import annotations

import argparse
import asyncio
import time

import httpx

from .common import USER_AGENT, atomic_write, fetch, get_logger, raw_dir, write_manifest

URL = "https://www.arbeitnow.com/api/job-board-api"
log = get_logger("arbeitnow")


async def main(concurrency: int, max_pages: int) -> None:
    started = time.time()
    out = raw_dir("arbeitnow")
    stats = {"requests": 0, "pages": 0, "jobs": 0, "bytes": 0}
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                                 timeout=60, follow_redirects=True) as client:

        async def get_page(n: int) -> bool:
            """Save page n; return True if there is a next page."""
            r = await fetch(client, URL, params={"page": n})
            stats["requests"] += 1
            r.raise_for_status()
            body = r.json()
            if not body.get("data"):
                return False
            atomic_write(out / f"page_{n:04d}.json", r.content)
            stats["pages"] += 1
            stats["jobs"] += len(body["data"])
            stats["bytes"] += len(r.content)
            return bool((body.get("links") or {}).get("next"))

        page = 1
        while page <= max_pages:
            batch = range(page, min(page + concurrency, max_pages + 1))
            has_next = await asyncio.gather(*(get_page(n) for n in batch))
            log.info("pages %d-%d fetched (%d jobs so far)", batch[0], batch[-1], stats["jobs"])
            if not all(has_next):
                break
            page += concurrency
            await asyncio.sleep(1)
    write_manifest("arbeitnow", stats, started)
    log.info("done: %s", stats)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--max-pages", type=int, default=200)
    a = ap.parse_args()
    asyncio.run(main(a.concurrency, a.max_pages))
