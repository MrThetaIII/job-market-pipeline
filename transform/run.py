"""Run the whole offline pipeline: raw -> jobs/rejects/job_skills parquet -> marts -> quality log.

    python -m transform.run
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from .dedupe import dedupe
from .enrich import enrich
from .normalize import RAW, ROOT, normalize

OUT = ROOT / "data" / "processed"
MARTS = OUT / "marts"
DASHBOARD_COLS = ["job_id", "source", "url", "title", "company", "location_raw", "country", "is_remote",
                  "posted_at", "role_family", "seniority", "salary_usd_min", "salary_usd_max"]


def main() -> None:
    t0 = time.time()
    MARTS.mkdir(parents=True, exist_ok=True)

    jobs, rejects = normalize()
    for j in jobs:  # one timezone everywhere, so dates compare cleanly
        p = j["posted_at"]
        j["posted_at"] = p.replace(tzinfo=timezone.utc) if p.tzinfo is None else p.astimezone(timezone.utc)
    print(f"normalize: {len(jobs):,} valid, {len(rejects):,} rejected  ({time.time() - t0:.0f}s)")

    pairs = dedupe(jobs)
    print(f"dedupe:    {len(pairs):,} cross-source duplicate pairs  ({time.time() - t0:.0f}s)")

    job_skills = enrich(jobs)
    print(f"enrich:    {len(job_skills):,} job-skill rows  ({time.time() - t0:.0f}s)")

    jobs_df = pd.DataFrame(jobs)
    jobs_df["posted_at"] = pd.to_datetime(jobs_df["posted_at"], utc=True).dt.tz_localize(None)
    for c in ("salary_min", "salary_max", "salary_usd_min", "salary_usd_max"):
        jobs_df[c] = pd.to_numeric(jobs_df[c], errors="coerce")
    jobs_df["is_remote"] = jobs_df["is_remote"].astype("boolean")
    rejects_df = pd.DataFrame(rejects, columns=["source", "source_id", "url", "reason", "sample"])
    skills_df = pd.DataFrame(job_skills, columns=["job_id", "skill", "category"])
    pairs_df = pd.DataFrame(pairs, columns=["job_id_a", "job_id_b", "source_a", "source_b",
                                            "company_score", "title_score"])
    jobs_df.to_parquet(OUT / "jobs.parquet", index=False)
    rejects_df.to_parquet(OUT / "rejects.parquet", index=False)
    skills_df.to_parquet(OUT / "job_skills.parquet", index=False)
    pairs_df.to_parquet(OUT / "duplicate_pairs.parquet", index=False)
    # Slim copy for the deployed dashboard: no descriptions, so it is a few MB instead of ~70
    # and the hosted app never republishes the boards' advert text.
    jobs_df[DASHBOARD_COLS].to_parquet(OUT / "dashboard_jobs.parquet", index=False)

    # ---- marts ----------------------------------------------------------------------
    con = duckdb.connect()
    con.execute(f"CREATE VIEW jobs AS SELECT * FROM read_parquet('{(OUT / 'jobs.parquet').as_posix()}')")
    con.execute(f"CREATE VIEW job_skills AS SELECT * FROM read_parquet('{(OUT / 'job_skills.parquet').as_posix()}')")
    sql = (ROOT / "analytics" / "marts.sql").read_text(encoding="utf-8")
    con.execute(sql)
    for name in re.findall(r"CREATE OR REPLACE TABLE (\w+)", sql):
        con.execute(f"COPY {name} TO '{(MARTS / (name + '.parquet')).as_posix()}' (FORMAT parquet)")
        print(f"mart:      {name:22s} {con.execute(f'SELECT count(*) FROM {name}').fetchone()[0]:>8,} rows")

    # ---- data quality log -----------------------------------------------------------
    raw_bytes = {d.name: sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
                 for d in RAW.iterdir() if d.is_dir()}
    rej_by = rejects_df.groupby(["source", "reason"]).size().rename("n").reset_index()
    quality = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sources": {}}
    track = ["location_raw", "country", "is_remote", "employment_type", "salary_usd_min"]
    for src, g in jobs_df.groupby("source"):
        n_rej = int((rejects_df["source"] == src).sum())
        quality["sources"][src] = {
            "raw_mb": round(raw_bytes.get(src, 0) / 1e6, 1),
            "valid_rows": len(g), "rejected_rows": n_rej,
            "reject_rate_pct": round(n_rej * 100 / max(len(g) + n_rej, 1), 2),
            "duplicates_of_other_source": int((~g["is_canonical"]).sum()),
            "missing_pct": {c: round(g[c].isna().mean() * 100, 1) for c in track},
            "posted_range": [str(g["posted_at"].min().date()), str(g["posted_at"].max().date())],
            "reject_reasons": {r.reason: int(r.n) for r in rej_by[rej_by["source"] == src].itertuples()},
        }
        if src == "hn":
            quality["sources"][src]["parse_method_pct"] = (
                g["parse_method"].value_counts(normalize=True).mul(100).round(1).to_dict())
    quality["collector_runs"] = [json.loads(line) for f in sorted(RAW.glob("*/*/_manifest.jsonl"))
                                 for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
    with (OUT / "quality_log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(quality) + "\n")
    (OUT / "quality_latest.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != 'reject_reasons'}
                      for k, v in quality["sources"].items()}, indent=1))
    print(f"total {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
