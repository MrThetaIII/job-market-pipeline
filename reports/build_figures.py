"""Render the 10 showcase figures from data/processed into reports/figures/*.png.

    python -m reports.build_figures

Every number on every figure is read from the parquet files / quality log, so the
pictures refresh themselves whenever the pipeline is rerun. Key numbers are also
dumped to reports/figures/facts.json for the write-up.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parent.parent
P = (ROOT / "data" / "processed").as_posix()
FIG = ROOT / "reports" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

# ---- palette (validated reference palette, light mode) ---------------------------------
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
BLUE_LIGHT, BLUE_DARK, NEUTRAL = "#b7d3f6", "#184f95", "#c3c2b7"
SRC_NAME = {"hn": "Hacker News", "remoteok": "RemoteOK", "arbeitnow": "Arbeitnow", "wwr": "We Work Remotely"}

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 11, "text.color": INK,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.axisbelow": True, "xtick.major.size": 0, "ytick.major.size": 0,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})

con = duckdb.connect()
con.execute(f"CREATE VIEW jobs AS SELECT * FROM '{P}/jobs.parquet'")
con.execute(f"CREATE VIEW job_skills AS SELECT * FROM '{P}/job_skills.parquet'")
con.execute(f"CREATE VIEW rejects AS SELECT * FROM '{P}/rejects.parquet'")
q = lambda sql: con.execute(sql).df()
quality = json.loads((ROOT / "data" / "processed" / "quality_latest.json").read_text(encoding="utf-8"))
facts: dict = {}
_n = [0]


def canvas(title: str, subtitle: str, *, axes: bool = True, top: float = 0.80, **adjust):
    fig = plt.figure(figsize=(12, 6.75), dpi=150)
    _n[0] += 1
    fig.text(0.05, 0.925, title, fontsize=19, fontweight="bold", va="center")
    fig.text(0.05, 0.868, subtitle, fontsize=11.5, color=INK2, va="center")
    fig.text(0.05, 0.03, "Source: job-market-pipeline · Hacker News “Who is hiring?”, RemoteOK, Arbeitnow, We Work Remotely",
             fontsize=8.5, color=MUTED)
    fig.text(0.95, 0.03, f"{_n[0]:02d} / 10", fontsize=8.5, color=MUTED, ha="right")
    ax = None
    if axes:
        ax = fig.add_subplot(111)
        fig.subplots_adjust(**{"left": 0.07, "right": 0.95, "top": top, "bottom": 0.12, **adjust})
    return fig, ax


def save(fig, name: str) -> None:
    fig.savefig(FIG / name)
    plt.close(fig)
    print("wrote", name)


def card(ax, x, y, w, h, fc="#ffffff", ec=GRID, lw=1.0):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.012",
                                fc=fc, ec=ec, lw=lw, transform=ax.transAxes, clip_on=False))


def blank_axes(fig):
    ax = fig.add_axes([0.05, 0.08, 0.90, 0.74])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    return ax


# ======================================================================================
# shared numbers
src = q("SELECT source, count(*) n, min(posted_at) lo, max(posted_at) hi FROM jobs GROUP BY 1").set_index("source")
total_jobs = int(src.n.sum())
raw_mb = sum(s["raw_mb"] for s in quality["sources"].values())
runs = quality["collector_runs"]
requests = {s: sum(r.get("requests", 0) for r in runs if r["source"] == s) for s in SRC_NAME}
hn_runs = [r for r in runs if r["source"] == "hn" and r.get("requests", 0) > 5000]
hn_rps = max((r.get("req_per_s", 0) for r in hn_runs), default=0)
n_skill_rows = int(q("SELECT count(*) c FROM job_skills").c[0])
n_threads = int(q("SELECT count(DISTINCT date_trunc('month', posted_at)) c FROM jobs WHERE source='hn'").c[0])
n_rejects = int(q("SELECT count(*) c FROM rejects").c[0])
first_year = int(src.loc["hn", "lo"].year)
last_year = int(src.loc["hn", "hi"].year)
facts.update(total_jobs=total_jobs, raw_mb=round(raw_mb, 1), requests=requests, hn_req_per_s=hn_rps,
             job_skill_rows=n_skill_rows, hn_months=n_threads, rejects=n_rejects,
             rows_by_source={k: int(v) for k, v in src.n.items()}, hn_years=[first_year, last_year])

# ======================================================================================
# 01  project at a glance
fig, _ = canvas("One pipeline, four job boards, fifteen years of tech hiring",
                "What was built: collectors → cleaning → enrichment → analytics tables → report and interactive dashboard", axes=False)
ax = blank_axes(fig)
tiles = [(f"{total_jobs:,}", "job posts in one clean table"), (f"{sum(requests.values()):,}", "HTTP requests made"),
         (f"{raw_mb:,.0f} MB", "raw responses kept on disk"), (f"{first_year}–{last_year}", f"{n_threads} monthly HN threads"),
         (f"{n_skill_rows:,}", "skill mentions tagged")]
w = 0.184
for i, (big, small) in enumerate(tiles):
    x = i * (w + 0.02)
    card(ax, x, 0.62, w, 0.34)
    ax.text(x + 0.018, 0.83, big, fontsize=22, fontweight="bold", va="center")
    ax.text(x + 0.018, 0.695, small, fontsize=10.5, color=INK2, va="center")
stages = [("1  Extract", "4 collectors\nasyncio + httpx\nraw files, untouched", BLUE),
          ("2  Normalize", "one jobs schema\nPydantic validation\nrejects table", BLUE),
          ("3  Dedupe", "rapidfuzz matching\n30-day window\nacross boards", BLUE),
          ("4  Enrich", "190-skill dictionary\nrole family, seniority\nsalary → annual USD", BLUE),
          ("5  Analyse & serve", "DuckDB analytics tables\n10-figure report\nStreamlit dashboard", BLUE)]
for i, (head, body, col) in enumerate(stages):
    x = i * (w + 0.02)
    card(ax, x, 0.08, w, 0.42, fc="#ffffff")
    ax.add_patch(FancyBboxPatch((x, 0.42), w, 0.08, boxstyle="round,pad=0,rounding_size=0.012", fc=col, ec=col,
                                transform=ax.transAxes, clip_on=False))
    ax.text(x + 0.018, 0.46, head, fontsize=12.5, fontweight="bold", color="#ffffff", va="center")
    ax.text(x + 0.018, 0.26, body, fontsize=10.5, color=INK2, va="center", linespacing=1.7)
    if i < 4:
        ax.add_patch(FancyArrowPatch((x + w + 0.002, 0.29), (x + w + 0.018, 0.29), transform=ax.transAxes,
                                     arrowstyle="-|>", mutation_scale=12, color=MUTED, lw=1.2, clip_on=False))
ax.text(0, 0.555, "THE PIPELINE", fontsize=9.5, color=MUTED, fontweight="bold")
save(fig, "01_project_at_a_glance.png")

# ======================================================================================
# 02  how each source was collected
fig, _ = canvas("Each source gets the access pattern it can tolerate",
                "Fast and parallel where an official API invites it; slow and sequential where we are a guest on someone's website",
                axes=False)
ax = blank_axes(fig)
rows = [("hn", "Official Firebase API\n+ Algolia thread search", "50 concurrent requests\n(asyncio semaphore)", f"≈{hn_rps:.0f} requests / second"),
        ("wwr", "HTML scraping\n(selectolax, JSON-LD)", "1 request at a time\n1–2 s pause, robots.txt checked", "pages cached, never refetched"),
        ("arbeitnow", "Public JSON API\npaginated", "3 pages at a time", "stops when links.next is empty"),
        ("remoteok", "Public JSON API\nsingle endpoint", "1 request per run", "legal notice row skipped")]
cols = [0.0, 0.2, 0.44, 0.70, 0.86]
for x, head in zip(cols, ["SOURCE", "HOW", "PARALLELISM", "REQUESTS", "CLEAN ROWS"]):
    ax.text(x + 0.015, 0.955, head, fontsize=9.5, color=MUTED, fontweight="bold")
max_rows = max(int(src.n.max()), 1)
for i, (s, how, par, note) in enumerate(rows):
    y = 0.72 - i * 0.235
    card(ax, 0, y, 1.0, 0.20)
    n = int(src.n.get(s, 0))
    ax.text(0.015, y + 0.125, SRC_NAME[s], fontsize=14, fontweight="bold", va="center")
    ax.text(0.015, y + 0.055, f"{quality['sources'].get(s, {}).get('raw_mb', 0):,.0f} MB raw", fontsize=10, color=INK2, va="center")
    ax.text(cols[1] + 0.015, y + 0.10, how, fontsize=10.5, color=INK2, va="center", linespacing=1.5)
    ax.text(cols[2] + 0.015, y + 0.125, par, fontsize=10.5, color=INK, va="center", linespacing=1.5)
    ax.text(cols[2] + 0.015, y + 0.04, note, fontsize=9.5, color=MUTED, va="center")
    ax.text(cols[3] + 0.015, y + 0.10, f"{requests.get(s, 0):,}", fontsize=17, fontweight="bold", va="center")
    ax.text(cols[4] + 0.015, y + 0.125, f"{n:,}", fontsize=17, fontweight="bold", va="center")
    bw = 0.11 * (n / max_rows) ** 0.5
    ax.add_patch(FancyBboxPatch((cols[4] + 0.015, y + 0.04), max(bw, 0.004), 0.022, boxstyle="round,pad=0,rounding_size=0.004",
                                fc=BLUE, ec=BLUE, transform=ax.transAxes, clip_on=False))
save(fig, "02_how_the_data_was_collected.png")

# ======================================================================================
# 03  cleaning HN: what happened to every comment
pm = q("SELECT parse_method, count(*) n FROM jobs WHERE source='hn' GROUP BY 1").set_index("parse_method").n
rj = q("SELECT reason, count(*) n FROM rejects WHERE source='hn' GROUP BY 1").set_index("reason").n
g = lambda s, keys: int(sum(s.get(k, 0) for k in keys))
steps = [("Pipe header, fully parsed", g(pm, ["pipe"]), BLUE),
         ("Pipe header + role found by regex", g(pm, ["pipe+regex_title", "pipe+no_title"]), BLUE),
         ("Dash / bullet separators", g(pm, ["alt_sep", "alt_sep+regex_title", "alt_sep+no_title"]), BLUE),
         ("Free text, regex only", g(pm, ["regex"]), BLUE),
         ("Rejected: no company or role found", g(rj, ["no_company_found", "no_title_found"]) + g(rj, [k for k in rj.index if ":" in k]), NEUTRAL),
         ("Deleted or flagged on HN", g(rj, ["deleted_or_dead"]), NEUTRAL)]
tot = sum(n for _, n, _ in steps)
kept = sum(n for _, n, c in steps if c == BLUE)
facts["hn_cleaning"] = {k: n for k, n, _ in steps} | {"total_comments": tot, "kept_pct": round(kept * 100 / tot, 1)}
fig, ax = canvas(f"{kept * 100 / tot:.0f}% of {tot:,} Hacker News comments became usable job records",
                 "How each top-level comment was handled. Posts follow a loose “Company | Role | Location | Remote | Salary” convention — not a schema",
                 left=0.30)
labels = [s[0] for s in steps][::-1]
vals = [s[1] for s in steps][::-1]
ax.barh(labels, vals, color=[s[2] for s in steps][::-1], height=0.62)
for i, v in enumerate(vals):
    ax.text(v + tot * 0.008, i, f"{v:,}   ({v * 100 / tot:.1f}%)", va="center", fontsize=11, color=INK)
ax.grid(False); ax.set_xticks([]); ax.spines["bottom"].set_visible(False)
ax.tick_params(axis="y", labelsize=11.5, labelcolor=INK)
ax.set_xlim(0, max(vals) * 1.22)
ax.text(0.99, 0.04, "Blue = kept     Grey = dropped, with the reason logged to a rejects table",
        transform=ax.transAxes, ha="right", fontsize=10, color=INK2)
save(fig, "03_cleaning_hacker_news.png")

# ======================================================================================
# 04  hiring volume over time
m = q("""SELECT date_trunc('month', posted_at)::DATE AS month, count(*) n FROM jobs WHERE source='hn'
         GROUP BY 1 HAVING count(*) > 20 ORDER BY 1""")
m = m.iloc[:-1] if len(m) > 2 and m.n.iloc[-1] < 0.75 * m.n.iloc[-2] else m     # drop a still-filling month
m["roll"] = m.n.rolling(12, min_periods=6).mean()
peak = m.loc[m.roll.idxmax()]
last = m.iloc[-1]
facts["volume"] = {"peak_month": str(peak.month)[:7], "peak_12m_avg": round(peak.roll), "latest_month": str(last.month)[:7],
                   "latest_12m_avg": round(last.roll), "drop_pct": round((1 - last.roll / peak.roll) * 100)}
fig, ax = canvas(f"Hiring posts are down {facts['volume']['drop_pct']}% from the {str(peak.month)[:4]} peak",
                 "Job posts per monthly “Who is hiring?” thread on Hacker News · thin line = each month, thick line = 12-month average")
ax.plot(m.month, m.n, color=BLUE_LIGHT, lw=1.2)
ax.plot(m.month, m.roll, color=BLUE, lw=2.6)
ax.scatter([peak.month, last.month], [peak.roll, last.roll], s=55, color=BLUE, zorder=5, edgecolor=SURFACE, lw=2)
ax.annotate(f"Peak: {peak.roll:,.0f} posts / month ({str(peak.month)[:7]})", (peak.month, peak.roll),
            xytext=(peak.month, m.n.max() * 1.07), ha="center", fontsize=11, fontweight="bold",
            arrowprops=dict(arrowstyle="-", color=MUTED, lw=1, shrinkB=6))
ax.annotate(f"{last.roll:,.0f}", (last.month, last.roll), xytext=(8, 0), textcoords="offset points", va="center",
            fontsize=11, fontweight="bold")
ax.set_ylim(0, m.n.max() * 1.16); ax.margins(x=0.04)
ax.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
save(fig, "04_hiring_volume.png")

# ======================================================================================
# 05  remote share
r = q("""SELECT year(posted_at) y, count(*) n, avg(CASE WHEN is_remote THEN 1.0 ELSE 0 END) * 100 pct
         FROM jobs WHERE source='hn' GROUP BY 1 HAVING count(*) > 300 ORDER BY 1""")
rpeak, rlast, rfirst = r.loc[r.pct.idxmax()], r.iloc[-1], r.iloc[0]
pre = r[r.y == 2019].pct.iloc[0] if (r.y == 2019).any() else None
facts["remote"] = {int(a): round(b, 1) for a, b in zip(r.y, r.pct)}
fig, ax = canvas(f"Remote hiring peaked at {rpeak.pct:.0f}% in {int(rpeak.y)} and has been sliding since",
                 "Share of Hacker News hiring posts that offer remote work, by year")
ax.plot(r.y, r.pct, color=BLUE, lw=2.6, marker="o", ms=7, mec=SURFACE, mew=2)
for row, dy in [(rfirst, 12), (rpeak, 12), (rlast, 12)] + ([(r[r.y == 2019].iloc[0], -20)] if pre else []):
    ax.annotate(f"{row.pct:.0f}%", (row.y, row.pct), xytext=(0, dy), textcoords="offset points", ha="center",
                fontsize=11.5, fontweight="bold")
if (r.y >= 2020).any() and (r.y <= 2019).any():
    ax.axvline(2019.6, color=AXIS, lw=1, ls=(0, (4, 3)))
    ax.text(2019.7, 4, "COVID-19", fontsize=9.5, color=MUTED)
ax.set_ylim(0, 100); ax.set_xticks(r.y); ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
save(fig, "05_remote_share.png")

# ======================================================================================
# skills by year (shared by 06, 07)
sy = q("""WITH tot AS (SELECT year(posted_at) y, count(*) n FROM jobs WHERE source='hn' GROUP BY 1 HAVING count(*) > 300)
          SELECT t.y, s.skill, count(*) * 100.0 / any_value(t.n) pct
          FROM jobs j JOIN job_skills s USING (job_id) JOIN tot t ON t.y = year(j.posted_at)
          WHERE j.source='hn' GROUP BY t.y, s.skill""")
years = sorted(sy.y.unique())


def series(skill):
    d = sy[sy.skill == skill].set_index("y").pct.reindex(years).fillna(0)
    return d


# 06  language & framework trends: small multiples
picks = ["Python", "TypeScript", "React", "Rust", "Go", "JavaScript", "Java", "Rails"]
fig, _ = canvas("Python and TypeScript took over; Java, JavaScript and Rails faded",
                "Share of Hacker News hiring posts mentioning each technology, by year · every panel uses the same scale", axes=False)
ymax = max(series(s).max() for s in picks) * 1.18
facts["skill_trend"] = {}
for i, s in enumerate(picks):
    a = fig.add_axes([0.06 + (i % 4) * 0.228, 0.47 - (i // 4) * 0.37, 0.19, 0.27])
    d = series(s)
    up = d.iloc[-1] >= d.iloc[0]
    col = BLUE if up else ORANGE
    a.fill_between(years, d.values, color=col, alpha=0.10, lw=0)
    a.plot(years, d.values, color=col, lw=2.2)
    a.scatter([years[0], years[-1]], [d.iloc[0], d.iloc[-1]], s=30, color=col, zorder=5, edgecolor=SURFACE, lw=1.5)
    a.text(years[-1], d.iloc[-1] + ymax * 0.07, f"{d.iloc[-1]:.0f}%", fontsize=10.5, fontweight="bold", ha="right")
    a.set_title(s, loc="left", fontsize=13, fontweight="bold", pad=8)
    a.set_ylim(0, ymax); a.set_xticks([years[0], years[-1]]); a.set_yticks([])
    a.set_xticklabels([f"{years[0]}: {d.iloc[0]:.0f}%", str(years[-1])])
    a.get_xticklabels()[0].set_ha("left"); a.get_xticklabels()[1].set_ha("right")
    a.grid(False); a.tick_params(labelsize=9.5)
    facts["skill_trend"][s] = [round(d.iloc[0], 1), round(d.max(), 1), round(d.iloc[-1], 1)]
for x, col, lab in [(0.80, BLUE, "higher than at the start"), (0.80, ORANGE, "lower than at the start")]:
    yy_ = 0.935 if col == BLUE else 0.90
    fig.text(x, yy_, "■", fontsize=11, color=col, va="center")
    fig.text(x + 0.014, yy_, lab, fontsize=10, color=INK2, va="center")
save(fig, "06_language_trends.png")

# 07  the AI wave
ai = q("""WITH tot AS (SELECT year(posted_at) y, count(*) n FROM jobs WHERE source='hn' GROUP BY 1 HAVING count(*) > 300)
          SELECT t.y,
                 count(DISTINCT j.job_id) FILTER (WHERE s.skill IN ('AI','ML','Machine Learning','Deep Learning','LLM','Generative AI','AI Agents','RAG','NLP','Computer Vision')) * 100.0 / any_value(t.n) any_ai,
                 count(DISTINCT j.job_id) FILTER (WHERE s.skill IN ('LLM','Generative AI','AI Agents','RAG')) * 100.0 / any_value(t.n) llm
          FROM tot t JOIN jobs j ON year(j.posted_at) = t.y AND j.source='hn' LEFT JOIN job_skills s USING (job_id)
          GROUP BY t.y ORDER BY 1""")
facts["ai"] = {int(y): [round(a, 1), round(b, 1)] for y, a, b in zip(ai.y, ai.any_ai, ai.llm)}
a0 = ai[ai.y == 2022].iloc[0] if (ai.y == 2022).any() else ai.iloc[0]
fig, ax = canvas(f"AI went from {a0.any_ai:.0f}% of hiring posts in {int(a0.y)} to {ai.any_ai.iloc[-1]:.0f}% in {int(ai.y.iloc[-1])}",
                 "Share of Hacker News hiring posts mentioning AI or machine-learning terms, by year", right=0.80)
ax.plot(ai.y, ai.any_ai, color=BLUE, lw=2.6, marker="o", ms=7, mec=SURFACE, mew=2)
ax.plot(ai.y, ai.llm, color=ORANGE, lw=2.6, marker="o", ms=7, mec=SURFACE, mew=2)
ax.text(ai.y.iloc[-1] + 0.25, ai.any_ai.iloc[-1], f"Any AI / ML term\n{ai.any_ai.iloc[-1]:.0f}%", va="center", fontsize=11, fontweight="bold", linespacing=1.4)
ax.text(ai.y.iloc[-1] + 0.25, ai.llm.iloc[-1], f"LLMs, agents,\ngenerative AI\n{ai.llm.iloc[-1]:.0f}%", va="center", fontsize=11, fontweight="bold", linespacing=1.4)
if (ai.y == 2022).any():
    ax.axvline(2022.9, color=AXIS, lw=1, ls=(0, (4, 3)))
    ax.text(2022.8, ax.get_ylim()[1] * 0.94, "ChatGPT launches (Nov 2022)", fontsize=9.5, color=MUTED, ha="right")
ax.set_ylim(0, None); ax.set_xticks(ai.y); ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
save(fig, "07_ai_wave.png")

# ======================================================================================
# 08  salary transparency
hy = q(f"SELECT * FROM '{P}/marts/hn_yearly.parquet' WHERE posts > 300 ORDER BY year")
facts["salary_disclosed"] = {int(y): float(v) for y, v in zip(hy.year, hy.salary_disclosed_pct)}
facts["median_salary"] = {int(y): float(v) for y, v in zip(hy.year, hy.median_salary_usd) if v == v}
lastp = hy.salary_disclosed_pct.iloc[-1]
ref = hy[hy.year == 2019].iloc[0] if (hy.year == 2019).any() else hy.iloc[0]
fig, ax = canvas(f"Pay transparency: {lastp:.0f}% of posts now state a salary, up from {ref.salary_disclosed_pct:.0f}% in {int(ref.year)}",
                 "Share of Hacker News hiring posts with a parseable salary figure, by year")
bars = ax.bar(hy.year, hy.salary_disclosed_pct, color=BLUE, width=0.68)
for x, v in zip(hy.year, hy.salary_disclosed_pct):
    ax.text(x, v + lastp * 0.02, f"{v:.0f}%", ha="center", fontsize=10.5, fontweight="bold" if x == hy.year.iloc[-1] else "normal")
ax.set_xticks(hy.year); ax.set_yticks([]); ax.grid(False); ax.set_ylim(0, hy.salary_disclosed_pct.max() * 1.15)
save(fig, "08_salary_transparency.png")

# ======================================================================================
# 09  salary premium by skill
sb = q(f"""SELECT * FROM '{P}/marts/salary_by_skill.parquet'
           WHERE n_with >= 40 AND skill NOT IN ('ML', 'Data Science') ORDER BY premium_usd DESC""")
top, bottom = sb.head(9), sb.tail(5)
show = __import__("pandas").concat([top, bottom]).drop_duplicates("skill").iloc[::-1]
base = float(sb.median_without.median())
facts["salary_premium"] = {r.skill: [int(r.median_with), int(r.median_without), int(r.n_with)] for r in show.itertuples()}
fig, ax = canvas(f"{top.skill.iloc[0]}, {top.skill.iloc[1]} and {top.skill.iloc[2]} posts advertise the highest pay",
                 "Median advertised salary (annual USD) in posts that mention a skill vs. posts that do not · posts since 2022 · n = posts with the skill",
                 left=0.20, right=0.93)
yy = range(len(show))
ax.hlines(yy, show.median_without, show.median_with, color=AXIS, lw=2)
ax.scatter(show.median_without, yy, s=70, color=NEUTRAL, zorder=4, edgecolor=SURFACE, lw=1.5, label="Posts without the skill")
ax.scatter(show.median_with, yy, s=90, color=BLUE, zorder=5, edgecolor=SURFACE, lw=1.5, label="Posts with the skill")
for i, r in enumerate(show.itertuples()):
    right = r.premium_usd >= 0
    ax.text(r.median_with + (2500 if right else -2500), i, f"${r.median_with / 1000:.0f}k", va="center",
            ha="left" if right else "right", fontsize=10.5, fontweight="bold")
ax.set_yticks(list(yy)); ax.set_yticklabels([f"{r.skill}  (n={r.n_with})" for r in show.itertuples()], fontsize=11, color=INK)
ax.grid(axis="y", visible=False); ax.grid(axis="x", visible=True)
ax.xaxis.set_major_formatter(lambda v, _: f"${v / 1000:.0f}k")
ax.legend(loc="lower right", frameon=False, fontsize=10.5)
ax.margins(x=0.12)
save(fig, "09_salary_by_skill.png")

# ======================================================================================
# 10  how the boards differ
GROUPS = {"Software Engineer": "Software engineering", "ML Engineer": "Data, ML & AI", "Data Scientist": "Data, ML & AI",
          "Data Engineer": "Data, ML & AI", "Data Analyst": "Data, ML & AI", "DevOps / Infrastructure": "DevOps & infrastructure",
          "Engineering Manager": "Engineering management", "Product": "Product & design", "Design": "Product & design",
          "Sales & Marketing": "Sales, marketing & support", "Customer Support": "Sales, marketing & support", "Other": "Other / non-tech"}
ORDER = ["Software engineering", "Data, ML & AI", "DevOps & infrastructure", "Engineering management", "Product & design",
         "Sales, marketing & support", "Other / non-tech"]
GCOL = dict(zip(ORDER, [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, NEUTRAL]))
sp = q(f"SELECT source, value, jobs FROM '{P}/marts/source_profile.parquet' WHERE dimension='role_family'")
sp["grp"] = sp.value.map(GROUPS)
pv = sp.pivot_table(index="source", columns="grp", values="jobs", aggfunc="sum").fillna(0).reindex(columns=ORDER).fillna(0)
pv = pv.div(pv.sum(axis=1), axis=0) * 100
pv = pv.reindex([s for s in ["arbeitnow", "wwr", "remoteok", "hn"] if s in pv.index])
facts["role_mix"] = {s: {k: round(v, 1) for k, v in pv.loc[s].items()} for s in pv.index}
fig, ax = canvas("Same job market, four very different windows onto it",
                 "Role mix of each board over the last 12 months · share of listings", left=0.16, top=0.74)
left = [0.0] * len(pv)
for gname in ORDER:
    v = pv[gname].values
    ax.barh(range(len(pv)), v, left=left, color=GCOL[gname], height=0.6, edgecolor=SURFACE, lw=2, label=gname)
    for i, (l, x) in enumerate(zip(left, v)):
        if x >= 6:
            ax.text(l + x / 2, i, f"{x:.0f}%", ha="center", va="center", fontsize=10.5, fontweight="bold",
                    color=INK if gname in ("Other / non-tech", "Product & design", "Engineering management") else "#ffffff")
    left = [a + b for a, b in zip(left, v)]
ax.set_yticks(range(len(pv))); ax.set_yticklabels([f"{SRC_NAME[s]}\n{int(src.n[s]):,} rows" for s in pv.index], fontsize=11, color=INK, linespacing=1.5)
ax.set_xlim(0, 100); ax.set_xticks([]); ax.grid(False); ax.spines["bottom"].set_visible(False)
ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=4, frameon=False, fontsize=10, handlelength=1, handleheight=1, columnspacing=1.6)
save(fig, "10_how_the_boards_differ.png")

(FIG / "facts.json").write_text(json.dumps(facts, indent=2, default=str), encoding="utf-8")
print(json.dumps(facts, indent=1, default=str))
