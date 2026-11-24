"""Capture dashboard screenshots for the showcase, each with its endpoint in an address bar.

Needs Playwright (dev-only dependency; it drives the Edge already installed on Windows,
so no browser download):   pip install playwright

    python -m reports.capture_dashboard                              # the deployed app
    python -m reports.capture_dashboard http://localhost:8501/       # a local run

English views go to reports/figures/, the Arabic interface (?lang=ar) to reports/figures_ar/.

Each view is just a URL, because the dashboard reads its filters from the query string.
The address bar drawn on top of every image shows exactly the URL that produced it.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import Frame, Page, sync_playwright

FIGS = {"en": Path(__file__).resolve().parent / "figures", "ar": Path(__file__).resolve().parent / "figures_ar"}
LIVE = "https://tech-hiring-2011-2026.streamlit.app/"
W, SCALE = 1440, 1.5

# file name -> (query string, heading to scroll to or None for the top, viewport height)
SHOTS = {
    "dash_1_overview.png": ("", None, 860),
    "dash_2_skills.png": ("", "Most mentioned skills", 620),
    "dash_3_roles_salary.png": ("", "Role mix", 600),
    "dash_4_filtered.png": ("?skill=Rust&remote=1&from=2018", None, 860),
    "dash_5_table.png": ("?skill=Rust&remote=1&from=2018", "Matching posts", 560),
    "dash_6_all_sources.png": ("?source=hn,wwr,arbeitnow,remoteok&from=2026", "Role mix", 600),
}
# headings as the Arabic interface shows them
HEADING_AR = {"Most mentioned skills": "المهارات الأكثر ذكرًا", "Role mix": "توزيع الوظائف",
              "Matching posts": "الإعلانات المطابقة"}


def with_lang(query: str, lang: str) -> str:
    if lang == "en":
        return query
    return (query + "&" if query else "?") + f"lang={lang}"


def label(heading: str, lang: str) -> str:
    return HEADING_AR[heading] if lang == "ar" else heading


def app_frame(page: Page) -> Frame:
    """Streamlit Community Cloud wraps the app in an iframe; locally it is the page itself."""
    page.wait_for_function(
        "() => [window, ...Array.from(window.frames)].some(w => { try { return w.document.querySelector('h1') } catch (e) { return false } })",
        timeout=180_000)
    for _ in range(120):
        for fr in page.frames:
            try:
                if fr.query_selector("h1") and fr.query_selector("[data-testid='stSidebar']"):
                    return fr
            except Exception:
                pass
        page.wait_for_timeout(500)
    raise RuntimeError("dashboard did not load")


def settle(fr: Frame, lang: str) -> None:
    fr.wait_for_selector(f"text={label('Matching posts', lang)}", timeout=120_000)
    fr.wait_for_function("document.querySelectorAll('canvas, svg.marks').length >= 5", timeout=120_000)
    fr.wait_for_function("!document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=120_000)
    fr.page.wait_for_timeout(2000)


def with_address_bar(png: bytes, url: str) -> Image.Image:
    shot = Image.open(io.BytesIO(png)).convert("RGB")
    bar_h = int(46 * SCALE)
    out = Image.new("RGB", (shot.width, shot.height + bar_h), "#e9e8e4")
    out.paste(shot, (0, bar_h))
    d = ImageDraw.Draw(out)
    pad, r = int(10 * SCALE), int(13 * SCALE)
    for i, col in enumerate(("#c3c2b7", "#c3c2b7", "#c3c2b7")):          # window dots
        cx = int((22 + i * 20) * SCALE)
        d.ellipse((cx - 6 * SCALE, bar_h / 2 - 6 * SCALE, cx + 6 * SCALE, bar_h / 2 + 6 * SCALE), fill=col)
    x0 = int(90 * SCALE)
    d.rounded_rectangle((x0, pad * 0.7, shot.width - pad * 2, bar_h - pad * 0.7), radius=r, fill="#fcfcfb")
    try:
        font = ImageFont.truetype("segoeui.ttf", int(15 * SCALE))
    except OSError:
        font = ImageFont.load_default()
    host, _, rest = url.partition("://")[2].partition("/")
    tx = x0 + int(16 * SCALE)
    d.text((tx, bar_h / 2), host, font=font, fill="#0b0b0b", anchor="lm")
    d.text((tx + d.textlength(host, font=font), bar_h / 2), "/" + rest, font=font, fill="#52514e", anchor="lm")
    d.line((0, bar_h - 1, shot.width, bar_h - 1), fill="#c3c2b7")
    return out


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else LIVE
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")
        for lang, fig in FIGS.items():
            fig.mkdir(exist_ok=True)
            for name, (query, heading, height) in SHOTS.items():
                query = with_lang(query, lang)
                page = browser.new_page(viewport={"width": W, "height": height}, device_scale_factor=SCALE,
                                        color_scheme="light")
                page.goto(base + query, wait_until="domcontentloaded", timeout=180_000)
                fr = app_frame(page)
                settle(fr, lang)
                if heading:
                    fr.evaluate("""(h) => { const el = [...document.querySelectorAll('h2,h3')].find(e => e.innerText.trim() === h);
                                            el.scrollIntoView({block: 'start'}); }""", label(heading, lang))
                    page.wait_for_timeout(1500)
                with_address_bar(page.screenshot(), base + query).save(fig / name)
                page.close()
                print("wrote", fig.name, name, base + query)
        browser.close()
