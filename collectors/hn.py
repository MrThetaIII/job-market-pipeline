"""Hacker News "Who is hiring?" collector.

1. Thread discovery  - Algolia HN search API (stories by the `whoishiring` account).
2. Comment download  - official Firebase API, one request per top-level comment,
                       asyncio + httpx with a global semaphore (default 50).

Raw layout (responses are stored byte-for-byte, one per line):
    data/raw/hn/{YYYY-MM-DD}/_threads.json          Algolia responses
    data/raw/hn/{YYYY-MM-DD}/thread_{id}.jsonl      line 1 = thread item, then one line per comment

Resumable: a thread that already has a finished file (on any date) is skipped, except
threads newer than --refresh-days, which are refetched because they still get comments.

    python -m collectors.hn                 # full backfill, then cheap daily top-ups
    python -m collectors.hn --limit 2       # smoke test on the 2 newest threads
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time

import httpx

from .common import RAW, USER_AGENT, atomic_write, fetch, get_logger, raw_dir, write_manifest

ALGOLIA = "https://hn.algolia.com/api/v1/search_by_date"
FIREBASE = "https://hacker-news.firebaseio.com/v0/item/{id}.json"
TITLE_RE = re.compile(r"^\s*Ask HN:\s*Who is hiring\?", re.I)

log = get_logger("hn")


async def discover_threads(client: httpx.AsyncClient) -> list[dict]:
    """Every monthly thread: [{id, title, created_at_i}], newest first."""
    threads, pages, page = [], [], 0
    while True:
        r = await fetch(client, ALGOLIA, params={
            "tags": "story,author_whoishiring", "hitsPerPage": 1000, "page": page})
        r.raise_for_status()
        pages.append(r.text)
        body = r.json()
        for h in body["hits"]:
            if TITLE_RE.search(h.get("title") or ""):
                threads.append({"id": int(h["objectID"]), "title": h["title"],
                                "created_at_i": h["created_at_i"]})
        page += 1
        if page >= body.get("nbPages", 1):
            break
    atomic_write(raw_dir("hn") / "_threads.json", "[" + ",".join(pages) + "]")
    threads.sort(key=lambda t: -t["created_at_i"])
    return threads


def already_done(thread_id: int) -> bool:
    return any((RAW / "hn").glob(f"*/thread_{thread_id}.jsonl"))


async def fetch_thread(client: httpx.AsyncClient, sem: asyncio.Semaphore,
                       thread: dict, stats: dict) -> None:
    async def get_item(item_id: int) -> str:
        async with sem:
            r = await fetch(client, FIREBASE.format(id=item_id))
            stats["requests"] += 1
            if r.status_code != 200:
                stats["errors"] += 1
                return ""
            return r.text.strip()

    root = await get_item(thread["id"])
    kids = (json.loads(root) or {}).get("kids", []) if root else []
    bodies = await asyncio.gather(*(get_item(k) for k in kids))
    lines = [root] + [b for b in bodies if b]
    payload = "\n".join(lines) + "\n"
    atomic_write(raw_dir("hn") / f"thread_{thread['id']}.jsonl", payload)
    stats["threads"] += 1
    stats["comments"] += len(lines) - 1
    stats["bytes"] += len(payload.encode("utf-8"))
    log.info("%s  %5d comments  (total %d comments, %.1f MB, %.0f req/s)",
             thread["title"][17:].strip(" ()"), len(lines) - 1, stats["comments"],
             stats["bytes"] / 1e6, stats["requests"] / max(time.time() - stats["t0"], 1e-9))


async def main(concurrency: int, limit: int | None, refresh_days: int, max_mb: float) -> None:
    started = time.time()
    stats = {"threads": 0, "comments": 0, "requests": 0, "errors": 0, "bytes": 0,
             "skipped": 0, "t0": started}
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=30,
                                 limits=limits) as client:
        threads = await discover_threads(client)
        log.info("discovered %d 'Who is hiring?' threads", len(threads))
        if limit:
            threads = threads[:limit]
        sem = asyncio.Semaphore(concurrency)
        cutoff = time.time() - refresh_days * 86400
        for t in threads:  # threads are sequential; the comments inside each are concurrent
            fresh = t["created_at_i"] >= cutoff
            if not fresh and already_done(t["id"]):
                stats["skipped"] += 1
                continue
            if stats["bytes"] / 1e6 >= max_mb:
                log.warning("hit --max-mb %.0f, stopping early", max_mb)
                break
            try:
                await fetch_thread(client, sem, t, stats)
            except Exception as e:  # keep the backfill going; the thread is retried next run
                stats["errors"] += 1
                log.error("thread %s failed: %r", t["id"], e)
    stats.pop("t0")
    stats["req_per_s"] = round(stats["requests"] / max(time.time() - started, 1e-9), 1)
    write_manifest("hn", stats, started)
    log.info("done: %s", stats)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=50)
    ap.add_argument("--limit", type=int, help="only the N newest threads (smoke test)")
    ap.add_argument("--refresh-days", type=int, default=45,
                    help="refetch threads younger than this even if already stored")
    ap.add_argument("--max-mb", type=float, default=400, help="stop after this much raw data")
    a = ap.parse_args()
    asyncio.run(main(a.concurrency, a.limit, a.refresh_days, a.max_mb))
