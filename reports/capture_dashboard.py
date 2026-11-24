"""Capture dashboard screenshots for the showcase.

Needs Playwright (dev-only dependency; it drives the Edge already installed on Windows,
so no browser download):   pip install playwright

Start the dashboard first (streamlit run dashboard/app.py), then:

    python -m reports.capture_dashboard

Each view is just a URL, because the dashboard reads its filters from the query string.
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

FIG = Path(__file__).resolve().parent / "figures"
BASE = "http://localhost:8501/"
W = 1440

# file name -> (query string, heading to scroll to or None for the top, viewport height)
SHOTS = {
    "dash_1_overview.png": ("", None, 860),
    "dash_2_skills.png": ("", "Most mentioned skills", 620),
    "dash_3_roles_salary.png": ("", "Role mix", 600),
    "dash_4_filtered.png": ("?skill=Rust&remote=1&from=2018", None, 860),
    "dash_5_table.png": ("?skill=Rust&remote=1&from=2018", "Matching posts", 560),
    "dash_6_all_sources.png": ("?source=hn,wwr,arbeitnow,remoteok&from=2026", "Role mix", 600),
}


def settle(page) -> None:
    page.wait_for_selector("h1", timeout=60_000)
    page.wait_for_selector("text=Matching posts", timeout=60_000)
    page.wait_for_function("document.querySelectorAll('canvas, svg.marks').length >= 5", timeout=60_000)
    page.wait_for_function("!document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=60_000)
    page.wait_for_timeout(1500)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")
    for name, (query, heading, height) in SHOTS.items():
        page = browser.new_page(viewport={"width": W, "height": height}, device_scale_factor=1.5,
                                color_scheme="light")
        page.goto(BASE + query)
        settle(page)
        if heading:
            page.get_by_role("heading", name=heading).scroll_into_view_if_needed()
            page.evaluate("""(h) => { const el = [...document.querySelectorAll('h2,h3')].find(e => e.innerText.trim() === h);
                                      el.scrollIntoView({block: 'start'}); }""", heading)
            page.wait_for_timeout(1200)
        page.screenshot(path=str(FIG / name))
        page.close()
        print("wrote", name)
    browser.close()
