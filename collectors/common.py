"""Shared helpers for all collectors: paths, User-Agent, retries, run manifests."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
LOGS = ROOT / "logs"

# Contact details are read from the environment so they never land in git.
# Set JOBMARKET_CONTACT to an email or URL, e.g.  $env:JOBMARKET_CONTACT = "you@example.com"
CONTACT = os.environ.get("JOBMARKET_CONTACT", "").strip()
USER_AGENT = "job-market-pipeline/0.1 (portfolio research project" + (
    f"; contact: {CONTACT})" if CONTACT else ")"
)

RETRY_STATUS = {429, 500, 502, 503, 504}


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def raw_dir(source: str, day: str | None = None) -> Path:
    d = RAW / source / (day or today())
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_logger(name: str) -> logging.Logger:
    LOGS.mkdir(exist_ok=True)
    log = logging.getLogger(name)
    if not log.handlers:
        log.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
        for h in (logging.StreamHandler(sys.stdout),
                  logging.FileHandler(LOGS / f"{name}.log", encoding="utf-8")):
            h.setFormatter(fmt)
            log.addHandler(h)
    return log


async def fetch(client: httpx.AsyncClient, url: str, *, retries: int = 6, **kw) -> httpx.Response:
    """GET with exponential backoff + jitter on network errors and 429/5xx."""
    delay = 1.0
    for attempt in range(retries + 1):
        try:
            r = await client.get(url, **kw)
            if r.status_code not in RETRY_STATUS:
                return r
            err: Exception | str = f"HTTP {r.status_code}"
            retry_after = r.headers.get("retry-after", "")
            if retry_after.isdigit():
                delay = max(delay, float(retry_after))
        except (httpx.TransportError, httpx.TimeoutException) as e:
            err = e
        if attempt == retries:
            raise RuntimeError(f"giving up on {url}: {err!r}")
        await asyncio.sleep(delay + random.random())
        delay = min(delay * 2, 60)
    raise AssertionError("unreachable")


def atomic_write(path: Path, data: bytes | str) -> None:
    """Write via a temp file so an interrupted run never leaves a half-written file."""
    tmp = path.with_name(path.name + ".tmp")
    if isinstance(data, str):
        tmp.write_text(data, encoding="utf-8")
    else:
        tmp.write_bytes(data)
    tmp.replace(path)


def write_manifest(source: str, stats: dict, started: float, day: str | None = None) -> None:
    """Append one line per run; the data quality log is built from these."""
    stats = {
        "source": source,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duration_s": round(time.time() - started, 1),
        **stats,
    }
    with (raw_dir(source, day) / "_manifest.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(stats) + "\n")
