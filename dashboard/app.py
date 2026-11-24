"""Job market dashboard.

    streamlit run dashboard/app.py

Reads data/processed/*.parquet only. Filters: source, role, skill, date range, remote.
"""
from __future__ import annotations

from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
P = (ROOT / "data" / "processed").as_posix()
BLUE, ORANGE, AQUA, YELLOW, MUTED = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#898781"
SERIES = [BLUE, ORANGE, AQUA, YELLOW, "#e87ba4", "#008300", "#6250d6", "#e34948"]
SRC_NAME = {"hn": "Hacker News", "remoteok": "RemoteOK", "arbeitnow": "Arbeitnow", "wwr": "We Work Remotely"}

st.set_page_config(page_title="Job market pipeline", page_icon="📊", layout="wide")

# The slim file (no descriptions) is what gets committed and deployed; fall back to the full table locally.
JOBS_FILE = next((f"{P}/{n}" for n in ("dashboard_jobs.parquet", "jobs.parquet")
                  if (ROOT / "data" / "processed" / n).exists()), None)
if JOBS_FILE is None:
    st.error("No processed data yet. Run `python -m transform.run` first.")
    st.stop()


@st.cache_data(show_spinner="Loading job posts…")
def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    con = duckdb.connect()
    jobs = con.execute(f"""
        SELECT job_id, source, url, title, company, location_raw, country, is_remote, posted_at,
               role_family, seniority, (salary_usd_min + salary_usd_max) / 2 AS salary_usd
        FROM '{JOBS_FILE}'""").df()
    jobs["month"] = jobs["posted_at"].dt.to_period("M").dt.to_timestamp()
    jobs["year"] = jobs["posted_at"].dt.year
    jobs["source_name"] = jobs["source"].map(SRC_NAME)
    skills = con.execute(f"SELECT job_id, skill, category FROM '{P}/job_skills.parquet'").df()
    return jobs, skills


jobs, skills = load()
skill_counts = skills["skill"].value_counts()

# ------------------------------------------------------------------ filters
# Filters start from the URL, so a view can be bookmarked or shared, e.g.
#   ?skill=Rust,Go&remote=1&from=2018&source=hn,wwr&role=Data%20Engineer
qp = st.query_params


def qp_list(key: str, allowed: list[str]) -> list[str]:
    return [v for v in qp.get(key, "").split(",") if v in allowed]


def qp_int(key: str, default: int, lo: int, hi: int) -> int:
    try:
        return min(max(int(qp.get(key, default)), lo), hi)
    except ValueError:
        return default


with st.sidebar:
    st.header("Filters")
    y0, y1 = int(jobs.year.min()), int(jobs.year.max())
    years = st.slider("Posted between", y0, y1, (qp_int("from", y0, y0, y1), qp_int("to", y1, y0, y1)))
    src_default = [SRC_NAME[s] for s in qp_list("source", list(SRC_NAME))] or ["Hacker News"]
    sources = st.multiselect("Source", list(SRC_NAME.values()), default=src_default,
                             help="Only Hacker News has history before the first collection day.")
    role_options = sorted(jobs.role_family.unique())
    roles = st.multiselect("Role family", role_options, default=qp_list("role", role_options))
    skill_options = skill_counts.index.tolist()
    pick_skills = st.multiselect("Skill (posts mentioning any of these)", skill_options,
                                 default=qp_list("skill", skill_options))
    remote_only = st.toggle("Remote only", value=qp.get("remote") == "1")
    st.caption("Leave a filter empty to include everything. Filters can also be set in the URL, "
               "e.g. `?skill=Rust&remote=1&from=2018`.")

f = jobs[jobs.year.between(*years)]
if sources:
    f = f[f.source_name.isin(sources)]
if roles:
    f = f[f.role_family.isin(roles)]
if pick_skills:
    f = f[f.job_id.isin(skills.loc[skills.skill.isin(pick_skills), "job_id"])]
if remote_only:
    f = f[f.is_remote.fillna(False).astype(bool)]
fs = skills[skills.job_id.isin(f.job_id)]

# ------------------------------------------------------------------ header + KPIs
st.title("Tech job market, 2011 – today")
st.caption("92k job posts from Hacker News “Who is hiring?”, RemoteOK, Arbeitnow and We Work Remotely. "
           "Counts are adverts, not hires.")
if f.empty:
    st.warning("No posts match these filters.")
    st.stop()

paid = f.dropna(subset=["salary_usd"])
k = st.columns(5)
k[0].metric("Job posts", f"{len(f):,}")
k[1].metric("Companies", f"{f.company.str.lower().nunique():,}")
k[2].metric("Remote", f"{f.is_remote.fillna(False).astype(bool).mean() * 100:.0f}%")
k[3].metric("State a salary", f"{len(paid) / len(f) * 100:.0f}%")
k[4].metric("Median salary", f"${paid.salary_usd.median() / 1000:,.0f}k" if len(paid) >= 20 else "n/a",
            help="Median of posts that state a salary; shown when at least 20 do.")


def base(df: pd.DataFrame) -> alt.Chart:
    return alt.Chart(df).properties(height=280)


TIP_MONTH = alt.Tooltip("month:T", title="Month", format="%b %Y")
multi_year = years[1] - years[0] >= 2

# ------------------------------------------------------------------ volume + remote
c1, c2 = st.columns(2)
with c1:
    st.subheader("Posts per month")
    m = f.groupby("month").size().rename("posts").reset_index()
    st.altair_chart(base(m).mark_line(color=BLUE, strokeWidth=2).encode(
        x=alt.X("month:T", title=None), y=alt.Y("posts:Q", title=None),
        tooltip=[TIP_MONTH, alt.Tooltip("posts:Q", title="Posts", format=",")]), use_container_width=True)
with c2:
    st.subheader("Share offering remote work")
    r = (f.assign(remote=f.is_remote.fillna(False).astype(bool)).groupby("year")
         .agg(pct=("remote", "mean"), posts=("remote", "size")).reset_index())
    r = r[r.posts >= 30]
    st.altair_chart(base(r).mark_line(color=BLUE, strokeWidth=2, point=alt.OverlayMarkDef(size=60, color=BLUE)).encode(
        x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("pct:Q", title=None, axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
        tooltip=[alt.Tooltip("year:O", title="Year"), alt.Tooltip("pct:Q", title="Remote", format=".0%"),
                 alt.Tooltip("posts:Q", title="Posts", format=",")]), use_container_width=True)

# ------------------------------------------------------------------ skills
c1, c2 = st.columns(2)
with c1:
    st.subheader("Most mentioned skills")
    top = (fs.groupby("skill").size() / len(f)).nlargest(15).rename("share").reset_index()
    st.altair_chart(alt.Chart(top).mark_bar(color=BLUE, cornerRadiusEnd=4).encode(
        x=alt.X("share:Q", title="Share of posts", axis=alt.Axis(format="%")),
        y=alt.Y("skill:N", sort="-x", title=None),
        tooltip=[alt.Tooltip("skill:N", title="Skill"), alt.Tooltip("share:Q", title="Share of posts", format=".1%")],
    ).properties(height=400), use_container_width=True)
with c2:
    st.subheader("Skill trend by year")
    default = pick_skills[:4] or [s for s in ["Python", "TypeScript", "Rust", "AI"] if s in fs.skill.values]
    trend_skills = st.multiselect("Compare up to four skills", skill_counts.index.tolist(), default=default,
                                  max_selections=4, label_visibility="collapsed")
    if trend_skills and multi_year:
        tot = f.groupby("year").size().rename("total")
        t = (fs[fs.skill.isin(trend_skills)].merge(f[["job_id", "year"]], on="job_id")
             .groupby(["year", "skill"]).size().rename("n").reset_index().merge(tot, on="year"))
        t = t[t.total >= 30].assign(share=lambda d: d.n / d.total)
        st.altair_chart(alt.Chart(t).mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=45)).encode(
            x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("share:Q", title="Share of posts", axis=alt.Axis(format="%")),
            color=alt.Color("skill:N", title=None, sort=trend_skills,
                            scale=alt.Scale(domain=trend_skills, range=SERIES[:len(trend_skills)]),
                            legend=alt.Legend(orient="top")),
            tooltip=[alt.Tooltip("year:O", title="Year"), alt.Tooltip("skill:N", title="Skill"),
                     alt.Tooltip("share:Q", title="Share of posts", format=".1%")],
        ).properties(height=360), use_container_width=True)
    else:
        st.info("Pick at least one skill and a range of two or more years to see a trend.")

# ------------------------------------------------------------------ roles + salary
c1, c2 = st.columns(2)
with c1:
    st.subheader("Role mix")
    rm = (f.groupby("role_family").size() / len(f)).rename("share").reset_index()
    st.altair_chart(alt.Chart(rm).mark_bar(color=BLUE, cornerRadiusEnd=4).encode(
        x=alt.X("share:Q", title="Share of posts", axis=alt.Axis(format="%")),
        y=alt.Y("role_family:N", sort="-x", title=None),
        tooltip=[alt.Tooltip("role_family:N", title="Role"), alt.Tooltip("share:Q", title="Share", format=".1%")],
    ).properties(height=360), use_container_width=True)
with c2:
    st.subheader("Advertised salary by role")
    sal = (paid.groupby("role_family").salary_usd
           .agg(n="size", p25=lambda s: s.quantile(.25), median="median", p75=lambda s: s.quantile(.75)).reset_index())
    sal = sal[sal.n >= 20]
    if sal.empty:
        st.info("Fewer than 20 posts with a salary in any role for these filters.")
    else:
        tips = [alt.Tooltip("role_family:N", title="Role"), alt.Tooltip("median:Q", title="Median", format="$,.0f"),
                alt.Tooltip("p25:Q", title="25th percentile", format="$,.0f"),
                alt.Tooltip("p75:Q", title="75th percentile", format="$,.0f"), alt.Tooltip("n:Q", title="Posts with salary")]
        enc = alt.Chart(sal).encode(y=alt.Y("role_family:N", sort=alt.SortField("median", order="descending"), title=None))
        st.altair_chart((enc.mark_rule(color="#b7d3f6", strokeWidth=6, strokeCap="round").encode(
            x=alt.X("p25:Q", title="Annual USD (bar = middle 50%, dot = median)", axis=alt.Axis(format="$~s"),
                    scale=alt.Scale(zero=False)), x2="p75:Q", tooltip=tips)
            + enc.mark_circle(color=BLUE, size=110, opacity=1).encode(x="median:Q", tooltip=tips)
        ).properties(height=360), use_container_width=True)
        st.caption("Only posts that state a salary; converted to annual USD with a fixed exchange-rate table.")

# ------------------------------------------------------------------ table
st.subheader("Matching posts")
show = (f.sort_values("posted_at", ascending=False).head(500)
        [["posted_at", "source_name", "company", "title", "role_family", "location_raw", "is_remote", "salary_usd", "url"]])
st.dataframe(show, use_container_width=True, hide_index=True, column_config={
    "posted_at": st.column_config.DateColumn("Posted"), "source_name": "Source", "company": "Company",
    "title": "Title", "role_family": "Role", "location_raw": "Location", "is_remote": "Remote",
    "salary_usd": st.column_config.NumberColumn("Salary (USD)", format="$%d"),
    "url": st.column_config.LinkColumn("Original listing", display_text="open")})
st.caption(f"Newest 500 of {len(f):,} matching posts. Every row links back to the original listing.")
