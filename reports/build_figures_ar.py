"""Render the Arabic versions of the 10 showcase figures into reports/figures_ar/*.png.

    python -m reports.build_figures_ar

Same data and the same numbers as reports/build_figures.py (the English script); only the
user-visible text is translated and the layouts are mirrored to read right-to-left where
that makes sense. Time axes still run left-to-right, as in Arabic print charts.
This script does not write facts.json and never touches reports/figures/.

Arabic text needs shaping (joined letter forms) and bidi reordering before matplotlib can
draw it; every Arabic string goes through A().
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import arabic_reshaper
import duckdb
import matplotlib
from bidi.algorithm import get_display

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch

ROOT = Path(__file__).resolve().parent.parent
P = (ROOT / "data" / "processed").as_posix()
FIG = ROOT / "reports" / "figures_ar"
FIG.mkdir(parents=True, exist_ok=True)

_ARABIC = re.compile("[؀-ۿݐ-ݿ]")


try:                                      # matplotlib >= 3.11 can lay text out with libraqm (shaping + bidi)
    from matplotlib.ft2font import __libraqm_version__ as _RAQM
except ImportError:
    _RAQM = ""
RLM = "‏"                             # right-to-left mark: forces an RTL paragraph direction


def A(s: str) -> str:
    """Prepare an Arabic string for matplotlib, line by line, with a right-to-left base direction.

    With libraqm, matplotlib shapes and reorders Arabic itself, so we only add an RLM (running
    arabic_reshaper/python-bidi as well would reverse the text a second time). Without libraqm
    we shape with arabic_reshaper and reorder with python-bidi.
    """
    if not _ARABIC.search(s):
        return s
    if _RAQM:
        return "\n".join(RLM + line for line in s.split("\n"))
    return "\n".join(get_display(arabic_reshaper.reshape(line), base_dir="R") for line in s.split("\n"))


MONTHS_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]


def month_ar(ts) -> str:
    return f"{MONTHS_AR[ts.month - 1]} {ts.year}"


# ---- palette (validated reference palette, light mode) ---------------------------------
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
BLUE_LIGHT, BLUE_DARK, NEUTRAL = "#b7d3f6", "#184f95", "#c3c2b7"
SRC_NAME = {"hn": "Hacker News", "remoteok": "RemoteOK", "arbeitnow": "Arbeitnow", "wwr": "We Work Remotely"}

plt.rcParams.update({
    "font.family": ["Segoe UI", "Tahoma", "DejaVu Sans"], "font.size": 11, "text.color": INK,
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
_n = [0]


def canvas(title: str, subtitle: str, *, axes: bool = True, top: float = 0.80, **adjust):
    fig = plt.figure(figsize=(12, 6.75), dpi=150)
    _n[0] += 1
    fig.text(0.95, 0.925, A(title), fontsize=19, fontweight="bold", va="center", ha="right")
    fig.text(0.95, 0.868, A(subtitle), fontsize=11.5, color=INK2, va="center", ha="right")
    fig.text(0.95, 0.03, A("المصدر: job-market-pipeline · خيوط «من يوظّف؟» على Hacker News، وRemoteOK، وArbeitnow، وWe Work Remotely"),
             fontsize=8.5, color=MUTED, ha="right")
    fig.text(0.05, 0.03, f"{_n[0]:02d} / 10", fontsize=8.5, color=MUTED, ha="left")
    ax = None
    if axes:
        ax = fig.add_subplot(111)
        fig.subplots_adjust(**{"left": 0.07, "right": 0.95, "top": top, "bottom": 0.12, **adjust})
    return fig, ax


def save(fig, name: str) -> None:
    for attempt in range(5):               # an image viewer holding the old PNG open can briefly block the write
        try:
            fig.savefig(FIG / name)
            break
        except OSError:
            if attempt == 4:
                raise
            time.sleep(1)
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

# ======================================================================================
# 01  project at a glance  (tiles and stages run right-to-left)
fig, _ = canvas("خط بيانات واحد، أربع منصات توظيف، خمسة عشر عامًا من التوظيف التقني",
                "ما الذي بُني: المُجمِّعات ← التنظيف ← الإثراء ← الجداول التحليلية ← التقرير ولوحة المعلومات التفاعلية",
                axes=False)
ax = blank_axes(fig)
tiles = [(f"{total_jobs:,}", "إعلان وظيفة في جدول نظيف"), (f"{sum(requests.values()):,}", "طلب HTTP مُنفَّذ"),
         (f"{raw_mb:,.0f} MB", "استجابات خام على القرص"), (f"{first_year}–{last_year}", f"{n_threads} خيطًا شهريًا على HN"),
         (f"{n_skill_rows:,}", "إشارة إلى مهارة تم وسمها")]
w = 0.184
xpos = lambda i: 1 - w - i * (w + 0.02)
for i, (big, small) in enumerate(tiles):
    x = xpos(i)
    card(ax, x, 0.62, w, 0.34)
    ax.text(x + w - 0.018, 0.83, A(big), fontsize=22, fontweight="bold", va="center", ha="right")
    ax.text(x + w - 0.018, 0.695, A(small), fontsize=10.5, color=INK2, va="center", ha="right")
stages = [("1  الاستخراج", "4 مُجمِّعات\nasyncio + httpx\nملفات خام دون أي تعديل", BLUE),
          ("2  التوحيد", "مخطط jobs واحد\nتحقُّق عبر Pydantic\nجدول للمرفوضات", BLUE),
          ("3  إزالة التكرار", "مطابقة عبر rapidfuzz\nنافذة 30 يومًا\nعبر المنصات", BLUE),
          ("4  الإثراء", "قاموس من 190 مهارة\nعائلة الدور والأقدمية\nالراتب ← دولار سنوي", BLUE),
          ("5  التحليل والعرض", "جداول تحليلية في DuckDB\nتقرير من 10 رسوم\nلوحة Streamlit", BLUE)]
for i, (head, body, col) in enumerate(stages):
    x = xpos(i)
    card(ax, x, 0.08, w, 0.42, fc="#ffffff")
    ax.add_patch(FancyBboxPatch((x, 0.42), w, 0.08, boxstyle="round,pad=0,rounding_size=0.012", fc=col, ec=col,
                                transform=ax.transAxes, clip_on=False))
    ax.text(x + w - 0.018, 0.46, A(head), fontsize=12.5, fontweight="bold", color="#ffffff", va="center", ha="right")
    ax.text(x + w - 0.018, 0.26, A(body), fontsize=10.5, color=INK2, va="center", ha="right", linespacing=1.7)
    if i < 4:
        ax.add_patch(FancyArrowPatch((x - 0.002, 0.29), (x - 0.018, 0.29), transform=ax.transAxes,
                                     arrowstyle="-|>", mutation_scale=12, color=MUTED, lw=1.2, clip_on=False))
ax.text(1, 0.555, A("خط البيانات"), fontsize=9.5, color=MUTED, fontweight="bold", ha="right")
save(fig, "01_project_at_a_glance.png")

# ======================================================================================
# 02  how each source was collected  (columns mirrored: source on the right)
fig, _ = canvas("كل مصدر يحصل على نمط الوصول الذي يحتمله",
                "سريع ومتوازٍ حيث تدعو إليه واجهة برمجية رسمية، وبطيء ومتسلسل حيث نكون ضيوفًا على موقع يملكه غيرنا",
                axes=False)
ax = blank_axes(fig)
rows = [("hn", "واجهة Firebase الرسمية\n+ البحث في الخيوط عبر Algolia", "50 طلبًا متزامنًا\n(asyncio semaphore)", f"نحو {hn_rps:.0f} طلبًا في الثانية"),
        ("wwr", "استخلاص صفحات HTML\n(selectolax و JSON-LD)", "طلب واحد في كل مرة\nتوقف 1 إلى 2 ثانية، مع فحص robots.txt", "الصفحات مخزنة ولا تُجلب مرتين"),
        ("arbeitnow", "واجهة JSON عامة\nمقسمة إلى صفحات", "3 صفحات في كل مرة", "يتوقف عندما يكون links.next فارغًا"),
        ("remoteok", "واجهة JSON عامة\nنقطة وصول واحدة", "طلب واحد في كل تشغيل", "يتم تخطي صف الإشعار القانوني")]
cols = [0.0, 0.2, 0.44, 0.70, 0.86]
R = [1 - c - 0.015 for c in cols]          # right-hand text anchor of each column
for x, head in zip(R, ["المصدر", "الطريقة", "التوازي", "الطلبات", "الصفوف النظيفة"]):
    ax.text(x, 0.955, A(head), fontsize=9.5, color=MUTED, fontweight="bold", ha="right")
max_rows = max(int(src.n.max()), 1)
for i, (s, how, par, note) in enumerate(rows):
    y = 0.72 - i * 0.235
    card(ax, 0, y, 1.0, 0.20)
    n = int(src.n.get(s, 0))
    ax.text(R[0], y + 0.125, SRC_NAME[s], fontsize=14, fontweight="bold", va="center", ha="right")
    ax.text(R[0], y + 0.055, A(f"{quality['sources'].get(s, {}).get('raw_mb', 0):,.0f} ميغابايت خام"), fontsize=10, color=INK2, va="center", ha="right")
    ax.text(R[1], y + 0.10, A(how), fontsize=10.5, color=INK2, va="center", ha="right", linespacing=1.5)
    ax.text(R[2], y + 0.125, A(par), fontsize=10.5, color=INK, va="center", ha="right", linespacing=1.5)
    ax.text(R[2], y + 0.04, A(note), fontsize=9.5, color=MUTED, va="center", ha="right")
    ax.text(R[3], y + 0.10, f"{requests.get(s, 0):,}", fontsize=17, fontweight="bold", va="center", ha="right")
    ax.text(R[4], y + 0.125, f"{n:,}", fontsize=17, fontweight="bold", va="center", ha="right")
    bw = max(0.11 * (n / max_rows) ** 0.5, 0.004)
    ax.add_patch(FancyBboxPatch((R[4] - bw, y + 0.04), bw, 0.022, boxstyle="round,pad=0,rounding_size=0.004",
                                fc=BLUE, ec=BLUE, transform=ax.transAxes, clip_on=False))
save(fig, "02_how_the_data_was_collected.png")

# ======================================================================================
# 03  cleaning HN: what happened to every comment  (bars grow right-to-left)
pm = q("SELECT parse_method, count(*) n FROM jobs WHERE source='hn' GROUP BY 1").set_index("parse_method").n
rj = q("SELECT reason, count(*) n FROM rejects WHERE source='hn' GROUP BY 1").set_index("reason").n
g = lambda s, keys: int(sum(s.get(k, 0) for k in keys))
steps = [("ترويسة بالشريط العمودي، تحليل كامل", g(pm, ["pipe"]), BLUE),
         ("ترويسة بالشريط العمودي + الدور عبر regex", g(pm, ["pipe+regex_title", "pipe+no_title"]), BLUE),
         ("فواصل بالشَّرطات أو النقاط", g(pm, ["alt_sep", "alt_sep+regex_title", "alt_sep+no_title"]), BLUE),
         ("نص حر، عبر regex فقط", g(pm, ["regex"]), BLUE),
         ("مرفوض: لم يُعثر على شركة أو دور", g(rj, ["no_company_found", "no_title_found"]) + g(rj, [k for k in rj.index if ":" in k]), NEUTRAL),
         ("محذوف أو مُعلَّم على HN", g(rj, ["deleted_or_dead"]), NEUTRAL)]
tot = sum(n for _, n, _ in steps)
kept = sum(n for _, n, c in steps if c == BLUE)
fig, ax = canvas(f"{kept * 100 / tot:.0f}% من {tot:,} تعليق على Hacker News أصبحت سجلات وظائف صالحة",
                 "كيف عولج كل تعليق رئيسي. تتبع الإعلانات عُرفًا فضفاضًا «الشركة | الدور | الموقع | عن بُعد | الراتب» — لا مخططًا ثابتًا",
                 left=0.05, right=0.68)
labels = [A(s[0]) for s in steps][::-1]
vals = [s[1] for s in steps][::-1]
ax.barh(labels, vals, color=[s[2] for s in steps][::-1], height=0.62)
for i, v in enumerate(vals):
    ax.text(v + tot * 0.008, i, f"{v:,}   ({v * 100 / tot:.1f}%)", va="center", ha="right", fontsize=11, color=INK)
ax.grid(False); ax.set_xticks([]); ax.spines["bottom"].set_visible(False)
ax.yaxis.tick_right()
ax.tick_params(axis="y", labelsize=11.5, labelcolor=INK)
ax.set_xlim(max(vals) * 1.22, 0)
ax.text(0.01, 0.04, A("الأزرق = محتفَظ به     الرمادي = مُستبعَد، مع تسجيل السبب في جدول للمرفوضات"),
        transform=ax.transAxes, ha="left", fontsize=10, color=INK2)
save(fig, "03_cleaning_hacker_news.png")

# ======================================================================================
# 04  hiring volume over time
m = q("""SELECT date_trunc('month', posted_at)::DATE AS month, count(*) n FROM jobs WHERE source='hn'
         GROUP BY 1 HAVING count(*) > 20 ORDER BY 1""")
m = m.iloc[:-1] if len(m) > 2 and m.n.iloc[-1] < 0.75 * m.n.iloc[-2] else m     # drop a still-filling month
m["roll"] = m.n.rolling(12, min_periods=6).mean()
peak = m.loc[m.roll.idxmax()]
last = m.iloc[-1]
drop_pct = round((1 - last.roll / peak.roll) * 100)
fig, ax = canvas(f"تراجعت إعلانات التوظيف بنسبة {drop_pct}% عن ذروة عام {str(peak.month)[:4]}",
                 "عدد إعلانات الوظائف في كل خيط شهري «من يوظّف؟» على Hacker News · الخط الرفيع = كل شهر، الخط السميك = متوسط 12 شهرًا")
ax.plot(m.month, m.n, color=BLUE_LIGHT, lw=1.2)
ax.plot(m.month, m.roll, color=BLUE, lw=2.6)
ax.scatter([peak.month, last.month], [peak.roll, last.roll], s=55, color=BLUE, zorder=5, edgecolor=SURFACE, lw=2)
ax.annotate(A(f"الذروة: {peak.roll:,.0f} إعلانًا شهريًا ({month_ar(peak.month)})"), (peak.month, peak.roll),
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
fig, ax = canvas(f"بلغ التوظيف عن بُعد ذروته عند {rpeak.pct:.0f}% في {int(rpeak.y)} ويتراجع منذ ذلك الحين",
                 "نسبة إعلانات التوظيف على Hacker News التي تتيح العمل عن بُعد، حسب السنة")
ax.plot(r.y, r.pct, color=BLUE, lw=2.6, marker="o", ms=7, mec=SURFACE, mew=2)
for row, dy in [(rfirst, 12), (rpeak, 12), (rlast, 12)] + ([(r[r.y == 2019].iloc[0], -20)] if pre else []):
    ax.annotate(f"{row.pct:.0f}%", (row.y, row.pct), xytext=(0, dy), textcoords="offset points", ha="center",
                fontsize=11.5, fontweight="bold")
if (r.y >= 2020).any() and (r.y <= 2019).any():
    ax.axvline(2019.6, color=AXIS, lw=1, ls=(0, (4, 3)))
    ax.text(2019.7, 4, A("جائحة كوفيد-19"), fontsize=9.5, color=MUTED)
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


# 06  language & framework trends: small multiples  (panels ordered right-to-left)
picks = ["Python", "TypeScript", "React", "Rust", "Go", "JavaScript", "Java", "Rails"]
fig, _ = canvas("تصدّرت Python وTypeScript، وتراجعت Java وJavaScript وRails",
                "نسبة إعلانات التوظيف على Hacker News التي تذكر كل تقنية، حسب السنة · جميع اللوحات بالمقياس نفسه", axes=False)
ymax = max(series(s).max() for s in picks) * 1.18
for i, s in enumerate(picks):
    a = fig.add_axes([0.06 + (3 - i % 4) * 0.228, 0.47 - (i // 4) * 0.37, 0.19, 0.27])
    d = series(s)
    up = d.iloc[-1] >= d.iloc[0]
    col = BLUE if up else ORANGE
    a.fill_between(years, d.values, color=col, alpha=0.10, lw=0)
    a.plot(years, d.values, color=col, lw=2.2)
    a.scatter([years[0], years[-1]], [d.iloc[0], d.iloc[-1]], s=30, color=col, zorder=5, edgecolor=SURFACE, lw=1.5)
    a.text(years[-1], d.iloc[-1] + ymax * 0.07, f"{d.iloc[-1]:.0f}%", fontsize=10.5, fontweight="bold", ha="right")
    a.set_title(s, loc="right", fontsize=13, fontweight="bold", pad=8)
    a.set_ylim(0, ymax); a.set_xticks([years[0], years[-1]]); a.set_yticks([])
    a.set_xticklabels([f"{years[0]}: {d.iloc[0]:.0f}%", str(years[-1])])
    a.get_xticklabels()[0].set_ha("left"); a.get_xticklabels()[1].set_ha("right")
    a.grid(False); a.tick_params(labelsize=9.5)
for col, lab, x_ in [(BLUE, "أعلى مما كانت عليه في البداية", 0.40), (ORANGE, "أدنى مما كانت عليه في البداية", 0.21)]:
    fig.text(x_, 0.815, "■", fontsize=11, color=col, va="center", ha="right")
    fig.text(x_ - 0.018, 0.815, A(lab), fontsize=10, color=INK2, va="center", ha="right")
save(fig, "06_language_trends.png")

# 07  the AI wave
ai = q("""WITH tot AS (SELECT year(posted_at) y, count(*) n FROM jobs WHERE source='hn' GROUP BY 1 HAVING count(*) > 300)
          SELECT t.y,
                 count(DISTINCT j.job_id) FILTER (WHERE s.skill IN ('AI','ML','Machine Learning','Deep Learning','LLM','Generative AI','AI Agents','RAG','NLP','Computer Vision')) * 100.0 / any_value(t.n) any_ai,
                 count(DISTINCT j.job_id) FILTER (WHERE s.skill IN ('LLM','Generative AI','AI Agents','RAG')) * 100.0 / any_value(t.n) llm
          FROM tot t JOIN jobs j ON year(j.posted_at) = t.y AND j.source='hn' LEFT JOIN job_skills s USING (job_id)
          GROUP BY t.y ORDER BY 1""")
a0 = ai[ai.y == 2022].iloc[0] if (ai.y == 2022).any() else ai.iloc[0]
fig, ax = canvas(f"قفز الذكاء الاصطناعي من {a0.any_ai:.0f}% من إعلانات التوظيف في {int(a0.y)} إلى {ai.any_ai.iloc[-1]:.0f}% في {int(ai.y.iloc[-1])}",
                 "نسبة إعلانات التوظيف على Hacker News التي تذكر مصطلحات الذكاء الاصطناعي أو تعلّم الآلة، حسب السنة", right=0.80)
ax.plot(ai.y, ai.any_ai, color=BLUE, lw=2.6, marker="o", ms=7, mec=SURFACE, mew=2)
ax.plot(ai.y, ai.llm, color=ORANGE, lw=2.6, marker="o", ms=7, mec=SURFACE, mew=2)
ax.text(ai.y.iloc[-1] + 0.35, ai.any_ai.iloc[-1], A(f"أي مصطلح للذكاء\nالاصطناعي أو تعلّم الآلة\n{ai.any_ai.iloc[-1]:.0f}%"),
        va="center", fontsize=11, fontweight="bold", linespacing=1.4, multialignment="right")
ax.text(ai.y.iloc[-1] + 0.35, ai.llm.iloc[-1], A(f"النماذج اللغوية الكبيرة\nوالوكلاء والذكاء\nالاصطناعي التوليدي\n{ai.llm.iloc[-1]:.0f}%"),
        va="center", fontsize=11, fontweight="bold", linespacing=1.4, multialignment="right")
if (ai.y == 2022).any():
    ax.axvline(2022.9, color=AXIS, lw=1, ls=(0, (4, 3)))
    ax.text(2022.8, ax.get_ylim()[1] * 0.94, A("إطلاق ChatGPT (نوفمبر 2022)"), fontsize=9.5, color=MUTED, ha="right")
ax.set_ylim(0, None); ax.set_xticks(ai.y); ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
save(fig, "07_ai_wave.png")

# ======================================================================================
# 08  salary transparency
hy = q(f"SELECT * FROM '{P}/marts/hn_yearly.parquet' WHERE posts > 300 ORDER BY year")
lastp = hy.salary_disclosed_pct.iloc[-1]
ref = hy[hy.year == 2019].iloc[0] if (hy.year == 2019).any() else hy.iloc[0]
fig, ax = canvas(f"شفافية الأجور: {lastp:.0f}% من الإعلانات تذكر الراتب الآن، بعد أن كانت {ref.salary_disclosed_pct:.0f}% في {int(ref.year)}",
                 "نسبة إعلانات التوظيف على Hacker News التي تتضمن رقمًا للراتب يمكن استخراجه، حسب السنة")
bars = ax.bar(hy.year, hy.salary_disclosed_pct, color=BLUE, width=0.68)
for x, v in zip(hy.year, hy.salary_disclosed_pct):
    ax.text(x, v + lastp * 0.02, f"{v:.0f}%", ha="center", fontsize=10.5, fontweight="bold" if x == hy.year.iloc[-1] else "normal")
ax.set_xticks(hy.year); ax.set_yticks([]); ax.grid(False); ax.set_ylim(0, hy.salary_disclosed_pct.max() * 1.15)
save(fig, "08_salary_transparency.png")

# ======================================================================================
# 09  salary premium by skill  (skill labels on the right)
sb = q(f"""SELECT * FROM '{P}/marts/salary_by_skill.parquet'
           WHERE n_with >= 40 AND skill NOT IN ('ML', 'Data Science') ORDER BY premium_usd DESC""")
top, bottom = sb.head(9), sb.tail(5)
show = __import__("pandas").concat([top, bottom]).drop_duplicates("skill").iloc[::-1]
fig, ax = canvas(f"إعلانات {top.skill.iloc[0]} و{top.skill.iloc[1]} و{top.skill.iloc[2]} تعرض أعلى الأجور",
                 "الراتب الوسيط المُعلَن (بالدولار الأمريكي سنويًا) في الإعلانات التي تذكر المهارة مقابل التي لا تذكرها · منذ 2022 · n = عدد الإعلانات التي تذكر المهارة",
                 left=0.05, right=0.78)
yy = range(len(show))
ax.hlines(yy, show.median_without, show.median_with, color=AXIS, lw=2)
ax.scatter(show.median_without, yy, s=70, color=NEUTRAL, zorder=4, edgecolor=SURFACE, lw=1.5, label=A("إعلانات لا تذكر المهارة"))
ax.scatter(show.median_with, yy, s=90, color=BLUE, zorder=5, edgecolor=SURFACE, lw=1.5, label=A("إعلانات تذكر المهارة"))
for i, r in enumerate(show.itertuples()):
    right = r.premium_usd >= 0
    ax.text(r.median_with + (2500 if right else -2500), i, f"${r.median_with / 1000:.0f}k", va="center",
            ha="left" if right else "right", fontsize=10.5, fontweight="bold")
ax.yaxis.tick_right()
ax.set_yticks(list(yy)); ax.set_yticklabels([f"{r.skill}  (n={r.n_with})" for r in show.itertuples()], fontsize=11, color=INK)
ax.grid(axis="y", visible=False); ax.grid(axis="x", visible=True)
ax.xaxis.set_major_formatter(lambda v, _: f"${v / 1000:.0f}k")
ax.legend(loc="lower right", frameon=False, fontsize=10.5, markerfirst=False)
ax.margins(x=0.12)
save(fig, "09_salary_by_skill.png")

# ======================================================================================
# 10  how the boards differ  (bars stack from the right)
GROUPS = {"Software Engineer": "Software engineering", "ML Engineer": "Data, ML & AI", "Data Scientist": "Data, ML & AI",
          "Data Engineer": "Data, ML & AI", "Data Analyst": "Data, ML & AI", "DevOps / Infrastructure": "DevOps & infrastructure",
          "Engineering Manager": "Engineering management", "Product": "Product & design", "Design": "Product & design",
          "Sales & Marketing": "Sales, marketing & support", "Customer Support": "Sales, marketing & support", "Other": "Other / non-tech"}
ORDER = ["Software engineering", "Data, ML & AI", "DevOps & infrastructure", "Engineering management", "Product & design",
         "Sales, marketing & support", "Other / non-tech"]
GROUP_AR = {"Software engineering": "هندسة البرمجيات", "Data, ML & AI": "البيانات وتعلّم الآلة والذكاء الاصطناعي",
            "DevOps & infrastructure": "DevOps والبنية التحتية", "Engineering management": "الإدارة الهندسية",
            "Product & design": "المنتج والتصميم", "Sales, marketing & support": "المبيعات والتسويق والدعم",
            "Other / non-tech": "أخرى / غير تقنية"}
GCOL = dict(zip(ORDER, [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, NEUTRAL]))
sp = q(f"SELECT source, value, jobs FROM '{P}/marts/source_profile.parquet' WHERE dimension='role_family'")
sp["grp"] = sp.value.map(GROUPS)
pv = sp.pivot_table(index="source", columns="grp", values="jobs", aggfunc="sum").fillna(0).reindex(columns=ORDER).fillna(0)
pv = pv.div(pv.sum(axis=1), axis=0) * 100
pv = pv.reindex([s for s in ["arbeitnow", "wwr", "remoteok", "hn"] if s in pv.index])
fig, ax = canvas("سوق العمل نفسه، وأربع نوافذ مختلفة جدًا عليه",
                 "مزيج الأدوار في كل منصة خلال آخر 12 شهرًا · نسبة الإعلانات", left=0.05, right=0.82, top=0.74)
left = [0.0] * len(pv)
handles = {}
for gname in ORDER:
    v = pv[gname].values
    handles[gname] = ax.barh(range(len(pv)), v, left=left, color=GCOL[gname], height=0.6, edgecolor=SURFACE, lw=2,
                             label=A(GROUP_AR[gname]))
    for i, (l, x) in enumerate(zip(left, v)):
        if x >= 6:
            ax.text(l + x / 2, i, f"{x:.0f}%", ha="center", va="center", fontsize=10.5, fontweight="bold",
                    color=INK if gname in ("Other / non-tech", "Product & design", "Engineering management") else "#ffffff")
    left = [a + b for a, b in zip(left, v)]
ax.yaxis.tick_right()
ax.set_yticks(range(len(pv)))
ax.set_yticklabels([A(f"{SRC_NAME[s]}\n{int(src.n[s]):,} صفًا") for s in pv.index], fontsize=11, color=INK, linespacing=1.5,
                   multialignment="right")
ax.set_xlim(100, 0); ax.set_xticks([]); ax.grid(False); ax.spines["bottom"].set_visible(False)
# legend reads right-to-left: lay the columns out mirrored, padding the grid with one invisible entry
blank = Patch(fc="none", ec="none", label=" ")
grid = [[ORDER[0], ORDER[4]], [ORDER[1], ORDER[5]], [ORDER[2], ORDER[6]], [ORDER[3], None]]
flat = [g for col in reversed(grid) for g in col]
ax.legend([handles[g] if g else blank for g in flat], [A(GROUP_AR[g]) if g else " " for g in flat],
          loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=4, frameon=False, fontsize=10, handlelength=1,
          handleheight=1, columnspacing=1.6, markerfirst=False)
save(fig, "10_how_the_boards_differ.png")
