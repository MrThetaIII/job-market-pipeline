"""RemoteOK collector: one request per run, raw response saved untouched.

    python -m collectors.remoteok

Note: element 0 of the response is RemoteOK's legal notice, not a job. It is kept in the
raw file (raw = untouched) and skipped in transform/normalize.py. Their terms ask for a
link back to the job URL on RemoteOK, which the `url` column preserves.
"""
from __future__ import annotations

import asyncio
import time

import httpx

from .common import USER_AGENT, atomic_write, fetch, get_logger, raw_dir, write_manifest

URL = "https://remoteok.com/api"
log = get_logger("remoteok")


async def main() -> None:
    started = time.time()
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=60,
                                 follow_redirects=True) as client:
        r = await fetch(client, URL)
        r.raise_for_status()
    stamp = time.strftime("%H%M%S", time.gmtime())
    atomic_write(raw_dir("remoteok") / f"api_{stamp}.json", r.content)
    jobs = max(len(r.json()) - 1, 0)
    write_manifest("remoteok", {"requests": 1, "jobs": jobs, "bytes": len(r.content)}, started)
    log.info("saved %d jobs (%.1f KB)", jobs, len(r.content) / 1e3)


if __name__ == "__main__":
    asyncio.run(main())
