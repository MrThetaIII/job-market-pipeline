"""Job market dashboard.

    streamlit run dashboard/app.py

Reads data/processed/*.parquet only. Filters: source, role, skill, date range, remote.
Interface in English or Arabic (sidebar switch, or ?lang=ar in the URL).
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

# ------------------------------------------------------------------ language
LANGS = {"en": "English", "ar": "العربية"}
lang = st.query_params.get("lang", "en")
lang = lang if lang in LANGS else "en"
AR = lang == "ar"

# Arabic strings; English is the key itself. Placeholders are filled with str.format.
AR_TEXT = {
    "Loading job posts…": "جارٍ تحميل إعلانات الوظائف…",
    "Language": "اللغة",
    "Filters": "عوامل التصفية",
    "Posted between": "تاريخ النشر بين",
    "Source": "المصدر",
    "Only Hacker News has history before the first collection day.":
        "\u200fHacker News وحده لديه بيانات تاريخية قبل أول يوم جمع.",
    "Role family": "فئة الوظيفة",
    "Skill (posts mentioning any of these)": "المهارة (الإعلانات التي تذكر أيًّا منها)",
    "Remote only": "العمل عن بُعد فقط",
    "Choose options": "اختر من القائمة",
    "Leave a filter empty to include everything. Filters can also be set in the URL, e.g. `?skill=Rust&remote=1&from=2018`.":
        "اترك عامل التصفية فارغًا لتضمين كل شيء. يمكن أيضًا ضبط عوامل التصفية في الرابط، مثل `?skill=Rust&remote=1&from=2018`.",
    "Tech job market, 2011 – today": "سوق الوظائف التقنية، من 2011 حتى اليوم",
    "92k job posts from Hacker News “Who is hiring?”, RemoteOK, Arbeitnow and We Work Remotely. Counts are adverts, not hires.":
        "\u200f92 ألف إعلان وظيفة من خيوط «Who is hiring?» على Hacker News ومن RemoteOK وArbeitnow وWe Work Remotely. "
        "الأرقام تعدّ الإعلانات لا التعيينات الفعلية.",
    "No posts match these filters.": "لا توجد إعلانات تطابق عوامل التصفية هذه.",
    "Job posts": "إعلانات الوظائف",
    "Companies": "الشركات",
    "Remote": "عن بُعد",
    "State a salary": "تذكر الراتب",
    "Median salary": "الراتب الوسيط",
    "n/a": "غير متاح",
    "Median of posts that state a salary; shown when at least 20 do.":
        "وسيط الإعلانات التي تذكر الراتب؛ يُعرض عندما يذكره 20 إعلانًا على الأقل.",
    "Month": "الشهر",
    "Posts": "الإعلانات",
    "Year": "السنة",
    "Posts per month": "الإعلانات شهريًا",
    "Share offering remote work": "نسبة الإعلانات التي تتيح العمل عن بُعد",
    "Most mentioned skills": "المهارات الأكثر ذكرًا",
    "Share of posts": "نسبة الإعلانات",
    "Skill": "المهارة",
    "Skill trend by year": "اتجاه المهارات حسب السنة",
    "Compare up to four skills": "قارن بين أربع مهارات كحدّ أقصى",
    "Pick at least one skill and a range of two or more years to see a trend.":
        "اختر مهارة واحدة على الأقل ونطاقًا من سنتين أو أكثر لعرض الاتجاه.",
    "Role mix": "توزيع الوظائف",
    "Role": "الوظيفة",
    "Share": "النسبة",
    "Advertised salary by role": "الراتب المُعلَن حسب الوظيفة",
    "Fewer than 20 posts with a salary in any role for these filters.":
        "أقل من 20 إعلانًا يذكر الراتب في كل وظيفة مع عوامل التصفية هذه.",
    "Median": "الوسيط",
    "25th percentile": "المئين 25",
    "75th percentile": "المئين 75",
    "Posts with salary": "إعلانات تذكر الراتب",
    "Annual USD (bar = middle 50%, dot = median)": "دولار أمريكي سنويًا (الشريط = الـ50% الوسطى، النقطة = الوسيط)",
    "Only posts that state a salary; converted to annual USD with a fixed exchange-rate table.":
        "الإعلانات التي تذكر الراتب فقط؛ حُوِّلت إلى دولار أمريكي سنوي بجدول أسعار صرف ثابت.",
    "Matching posts": "الإعلانات المطابقة",
    "Posted": "تاريخ النشر",
    "Company": "الشركة",
    "Title": "المسمّى الوظيفي",
    "Location": "الموقع",
    "Salary (USD)": "الراتب (دولار أمريكي)",
    "Original listing": "الإعلان الأصلي",
    "open": "فتح",
    "Newest 500 of {n} matching posts. Every row links back to the original listing.":
        "أحدث 500 من أصل {n} إعلانًا مطابقًا. كل صف يرتبط بالإعلان الأصلي.",
    "No processed data yet. Run `python -m transform.run` first.":
        "لا توجد بيانات معالَجة بعد. شغّل `python -m transform.run` أولًا.",
}
ROLE_AR = {
    "Software Engineer": "مهندس برمجيات", "Other": "أخرى", "DevOps / Infrastructure": "DevOps / البنية التحتية",
    "ML Engineer": "مهندس تعلّم آلي", "Engineering Manager": "مدير هندسي", "Data Scientist": "عالم بيانات",
    "Data Engineer": "مهندس بيانات", "Sales & Marketing": "المبيعات والتسويق", "Design": "التصميم",
    "Product": "إدارة المنتجات", "Data Analyst": "محلل بيانات", "Customer Support": "دعم العملاء",
}


def T(text: str, **kw) -> str:
    out = AR_TEXT.get(text, text) if AR else text
    return out.format(**kw) if kw else out


def role_label(role: str) -> str:
    return ROLE_AR.get(role, role) if AR else role


if AR:
    # Right-to-left page; charts, tables, sliders and code keep left-to-right.
    st.markdown("""<style>
      .stMain .block-container, [data-testid="stSidebar"] { direction: rtl; text-align: right; }
      .stMain [data-testid="stElementContainer"], [data-testid="stSidebar"] [data-testid="stElementContainer"],
      .stMain h1, .stMain h2, .stMain h3, [data-testid="stSidebar"] h2 { text-align: right; }
      [data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"], [data-testid="stDataFrame"],
      [data-testid="stSliderThumbValue"], [data-testid="stSlider"] [data-baseweb="slider"], code { direction: ltr; }
      [data-testid="stMetricValue"] { direction: ltr; text-align: right; }
    </style>""", unsafe_allow_html=True)

# The slim file (no descriptions) is what gets committed and deployed; fall back to the full table locally.
JOBS_FILE = next((f"{P}/{n}" for n in ("dashboard_jobs.parquet", "jobs.parquet")
                  if (ROOT / "data" / "processed" / n).exists()), None)
if JOBS_FILE is None:
    st.error(T("No processed data yet. Run `python -m transform.run` first."))
    st.stop()


@st.cache_data(show_spinner=False)
def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    con = duckdb.connect()
    jobs = con.execute(f"""
        SELECT job_id, source, url, title, company, location_raw, country, is_remote, posted_at,
               role_family, seniority, (salary_usd_min + salary_usd_max) / 2 AS salary_usd
        FROM '{JOBS_FILE}'""").df()
    jobs["month"] = jobs["posted_at"].dt.to_period("M").dt.to_timestamp()
    jobs["year"] = jobs["posted_at"].dt.year
    jobs["source_name"] = jobs["source"].map(SRC_NAME)
    jobs["role_family_ar"] = jobs["role_family"].map(ROLE_AR).fillna(jobs["role_family"])
    skills = con.execute(f"SELECT job_id, skill, category FROM '{P}/job_skills.parquet'").df()
    return jobs, skills


with st.spinner(T("Loading job posts…")):
    jobs, skills = load()
ROLE_COL = "role_family_ar" if AR else "role_family"
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
    picked = st.radio(T("Language"), list(LANGS), index=list(LANGS).index(lang), format_func=LANGS.get,
                      horizontal=True)
    if picked != lang:
        st.query_params["lang"] = picked
        st.rerun()
    st.header(T("Filters"))
    y0, y1 = int(jobs.year.min()), int(jobs.year.max())
    years = st.slider(T("Posted between"), y0, y1, (qp_int("from", y0, y0, y1), qp_int("to", y1, y0, y1)))
    src_default = [SRC_NAME[s] for s in qp_list("source", list(SRC_NAME))] or ["Hacker News"]
    sources = st.multiselect(T("Source"), list(SRC_NAME.values()), default=src_default, placeholder=T("Choose options"),
                             help=T("Only Hacker News has history before the first collection day."))
    role_options = sorted(jobs.role_family.unique())
    roles = st.multiselect(T("Role family"), role_options, default=qp_list("role", role_options), placeholder=T("Choose options"),
                           format_func=role_label)
    skill_options = skill_counts.index.tolist()
    pick_skills = st.multiselect(T("Skill (posts mentioning any of these)"), skill_options,
                                 default=qp_list("skill", skill_options),
                                 placeholder=T("Choose options"))
    remote_only = st.toggle(T("Remote only"), value=qp.get("remote") == "1")
    st.caption(T("Leave a filter empty to include everything. Filters can also be set in the URL, "
                 "e.g. `?skill=Rust&remote=1&from=2018`."))

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
st.title(T("Tech job market, 2011 – today"))
st.caption(T("92k job posts from Hacker News “Who is hiring?”, RemoteOK, Arbeitnow and We Work Remotely. "
             "Counts are adverts, not hires."))
if f.empty:
    st.warning(T("No posts match these filters."))
    st.stop()

paid = f.dropna(subset=["salary_usd"])
k = st.columns(5)
k[0].metric(T("Job posts"), f"{len(f):,}")
k[1].metric(T("Companies"), f"{f.company.str.lower().nunique():,}")
k[2].metric(T("Remote"), f"{f.is_remote.fillna(False).astype(bool).mean() * 100:.0f}%")
k[3].metric(T("State a salary"), f"{len(paid) / len(f) * 100:.0f}%")
k[4].metric(T("Median salary"), f"${paid.salary_usd.median() / 1000:,.0f}k" if len(paid) >= 20 else T("n/a"),
            help=T("Median of posts that state a salary; shown when at least 20 do."))


def base(df: pd.DataFrame) -> alt.Chart:
    return alt.Chart(df).properties(height=280)


TIP_MONTH = alt.Tooltip("month:T", title=T("Month"), format="%Y-%m" if AR else "%b %Y")
multi_year = years[1] - years[0] >= 2

# ------------------------------------------------------------------ volume + remote
c1, c2 = st.columns(2)
with c1:
    st.subheader(T("Posts per month"))
    m = f.groupby("month").size().rename("posts").reset_index()
    st.altair_chart(base(m).mark_line(color=BLUE, strokeWidth=2).encode(
        x=alt.X("month:T", title=None), y=alt.Y("posts:Q", title=None),
        tooltip=[TIP_MONTH, alt.Tooltip("posts:Q", title=T("Posts"), format=",")]), use_container_width=True)
with c2:
    st.subheader(T("Share offering remote work"))
    r = (f.assign(remote=f.is_remote.fillna(False).astype(bool)).groupby("year")
         .agg(pct=("remote", "mean"), posts=("remote", "size")).reset_index())
    r = r[r.posts >= 30]
    st.altair_chart(base(r).mark_line(color=BLUE, strokeWidth=2, point=alt.OverlayMarkDef(size=60, color=BLUE)).encode(
        x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("pct:Q", title=None, axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
        tooltip=[alt.Tooltip("year:O", title=T("Year")), alt.Tooltip("pct:Q", title=T("Remote"), format=".0%"),
                 alt.Tooltip("posts:Q", title=T("Posts"), format=",")]), use_container_width=True)

# ------------------------------------------------------------------ skills
c1, c2 = st.columns(2)
with c1:
    st.subheader(T("Most mentioned skills"))
    top = (fs.groupby("skill").size() / len(f)).nlargest(15).rename("share").reset_index()
    st.altair_chart(alt.Chart(top).mark_bar(color=BLUE, cornerRadiusEnd=4).encode(
        x=alt.X("share:Q", title=T("Share of posts"), axis=alt.Axis(format="%")),
        y=alt.Y("skill:N", sort="-x", title=None),
        tooltip=[alt.Tooltip("skill:N", title=T("Skill")), alt.Tooltip("share:Q", title=T("Share of posts"), format=".1%")],
    ).properties(height=400), use_container_width=True)
with c2:
    st.subheader(T("Skill trend by year"))
    default = pick_skills[:4] or [s for s in ["Python", "TypeScript", "Rust", "AI"] if s in fs.skill.values]
    trend_skills = st.multiselect(T("Compare up to four skills"), skill_counts.index.tolist(), default=default,
                                  max_selections=4, label_visibility="collapsed",
                                  placeholder=T("Choose options"))
    if trend_skills and multi_year:
        tot = f.groupby("year").size().rename("total")
        t = (fs[fs.skill.isin(trend_skills)].merge(f[["job_id", "year"]], on="job_id")
             .groupby(["year", "skill"]).size().rename("n").reset_index().merge(tot, on="year"))
        t = t[t.total >= 30].assign(share=lambda d: d.n / d.total)
        st.altair_chart(alt.Chart(t).mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=45)).encode(
            x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("share:Q", title=T("Share of posts"), axis=alt.Axis(format="%")),
            color=alt.Color("skill:N", title=None, sort=trend_skills,
                            scale=alt.Scale(domain=trend_skills, range=SERIES[:len(trend_skills)]),
                            legend=alt.Legend(orient="top")),
            tooltip=[alt.Tooltip("year:O", title=T("Year")), alt.Tooltip("skill:N", title=T("Skill")),
                     alt.Tooltip("share:Q", title=T("Share of posts"), format=".1%")],
        ).properties(height=360), use_container_width=True)
    else:
        st.info(T("Pick at least one skill and a range of two or more years to see a trend."))

# ------------------------------------------------------------------ roles + salary
c1, c2 = st.columns(2)
with c1:
    st.subheader(T("Role mix"))
    rm = (f.groupby(ROLE_COL).size() / len(f)).rename("share").reset_index()
    st.altair_chart(alt.Chart(rm).mark_bar(color=BLUE, cornerRadiusEnd=4).encode(
        x=alt.X("share:Q", title=T("Share of posts"), axis=alt.Axis(format="%")),
        y=alt.Y(f"{ROLE_COL}:N", sort="-x", title=None),
        tooltip=[alt.Tooltip(f"{ROLE_COL}:N", title=T("Role")), alt.Tooltip("share:Q", title=T("Share"), format=".1%")],
    ).properties(height=360), use_container_width=True)
with c2:
    st.subheader(T("Advertised salary by role"))
    sal = (paid.groupby(ROLE_COL).salary_usd
           .agg(n="size", p25=lambda s: s.quantile(.25), median="median", p75=lambda s: s.quantile(.75)).reset_index())
    sal = sal[sal.n >= 20]
    if sal.empty:
        st.info(T("Fewer than 20 posts with a salary in any role for these filters."))
    else:
        tips = [alt.Tooltip(f"{ROLE_COL}:N", title=T("Role")),
                alt.Tooltip("median:Q", title=T("Median"), format="$,.0f"),
                alt.Tooltip("p25:Q", title=T("25th percentile"), format="$,.0f"),
                alt.Tooltip("p75:Q", title=T("75th percentile"), format="$,.0f"),
                alt.Tooltip("n:Q", title=T("Posts with salary"))]
        enc = alt.Chart(sal).encode(y=alt.Y(f"{ROLE_COL}:N", sort=alt.SortField("median", order="descending"), title=None))
        st.altair_chart((enc.mark_rule(color="#b7d3f6", strokeWidth=6, strokeCap="round").encode(
            x=alt.X("p25:Q", title=T("Annual USD (bar = middle 50%, dot = median)"), axis=alt.Axis(format="$~s"),
                    scale=alt.Scale(zero=False)), x2="p75:Q", tooltip=tips)
            + enc.mark_circle(color=BLUE, size=110, opacity=1).encode(x="median:Q", tooltip=tips)
        ).properties(height=360), use_container_width=True)
        st.caption(T("Only posts that state a salary; converted to annual USD with a fixed exchange-rate table."))

# ------------------------------------------------------------------ table
st.subheader(T("Matching posts"))
show = (f.sort_values("posted_at", ascending=False).head(500)
        [["posted_at", "source_name", "company", "title", ROLE_COL, "location_raw", "is_remote", "salary_usd", "url"]])
st.dataframe(show, use_container_width=True, hide_index=True, column_config={
    "posted_at": st.column_config.DateColumn(T("Posted")), "source_name": T("Source"), "company": T("Company"),
    "title": T("Title"), ROLE_COL: T("Role"), "location_raw": T("Location"), "is_remote": T("Remote"),
    "salary_usd": st.column_config.NumberColumn(T("Salary (USD)"), format="$%d"),
    "url": st.column_config.LinkColumn(T("Original listing"), display_text=T("open"))})
st.caption(T("Newest 500 of {n} matching posts. Every row links back to the original listing.", n=f"{len(f):,}"))
