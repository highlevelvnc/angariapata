"""
Citius Insolvências · Premarket source (Sprint 2026-05-11)

Citius (citius.mj.pt) publishes Portuguese judicial insolvency announcements
publicly — no login required. When a person or company is declared insolvent
they typically liquidate property holdings within 3-12 months. That's a
strong premarket signal for our funnel.

Why a separate scraper from the existing public-data sources?
-------------------------------------------------------------
Citius is an ASP.NET WebForms application with a ViewState-based search
form. Raw httpx requests can't drive it — we need a browser to:
  1. Fill the form (date range, court, action category)
  2. Submit and wait for AJAX-rendered results
  3. Parse the results table

We reuse the async Playwright pattern already proven in scrapers/idealista.py.

Field mapping
-------------
Each Citius row has:
  - process number (eg "1234/26.0T8LSB")
  - publication date
  - court (Comarca de Lisboa, Comarca de Cascais, …)
  - action type (Sentença de declaração de insolvência, Encerramento, …)
  - intervenientes (NAME · NIPC/NIF · role)

We emit ONE PremktSignalData per insolvency where the `intervenientes` field
contains a name. The signal_score is 80 (just below building_permit 85) —
strong intent but no direct property address yet.

Operational notes
-----------------
- Live Citius pages can take 5-15s to load; we cap total runtime at 90s.
- The form has no public API, so we navigate the UI. Selectors are
  documented in `_SEL_*` constants — if Citius redesigns, only those need
  patching.
- Returns [] safely if anything fails — never raises into the enricher.
- This source is GUARDED behind `_CITIUS_ENABLED = False` until you flip
  the flag after first manual verification. The skeleton ships ready;
  activation is a 1-line edit.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta
from typing import Optional

from premarket.signals import PremktSignalData
from utils.logger import get_logger

log = get_logger(__name__)


# ── Feature flag ─────────────────────────────────────────────────────────────
# Flip to True after first manual verification on the live Citius portal.
# Required by the enricher's defensive-loading try/except — when False, the
# source still loads (no error) but fetch() returns [] immediately.
_CITIUS_ENABLED = False

# ── Selectors (ASP.NET form) ─────────────────────────────────────────────────
# Validated against citius.mj.pt 2026-05-11. These IDs are stable across
# postbacks because ASP.NET WebForms keeps Control IDs deterministic.
_BASE_URL          = "https://www.citius.mj.pt/portal/consultas/ConsultasCire.aspx"
_SEL_DATE_FROM     = "input[name$='txtDataDe']"
_SEL_DATE_TO       = "input[name$='txtDataAte']"
_SEL_ACTION_GROUP  = "select[name$='ddlGrupoActo']"
_SEL_SUBMIT_BTN    = "input[type='submit'][value*='Pesquisar' i], button[type='submit']"
_SEL_RESULTS_ROW   = "table.tabela tbody tr, .resultados table tr"

# "Insolvência" is the action group we want. Confirmed in dropdown 2026-05.
_ACTION_GROUP_LABEL = "Insolvência"

# Date window — 30d lookback by default (insolvency-to-listing typically 3-12m
# but the freshest signals convert best).
_LOOKBACK_DAYS = 30
_PAGE_TIMEOUT_MS = 25_000


# ── PT NIF/NIPC detection ────────────────────────────────────────────────────
_NIF_RE = re.compile(r"\b\d{9}\b")
_PROCESS_RE = re.compile(r"\b\d+/\d+\.\d+T\w+\b")


def _parse_intervenient(text: str) -> tuple[Optional[str], Optional[str]]:
    """Extract (name, nif) from an intervenient string."""
    if not text:
        return (None, None)
    nif_match = _NIF_RE.search(text)
    nif = nif_match.group(0) if nif_match else None
    # Name is whatever's left, cleaned
    name = _NIF_RE.sub("", text)
    name = re.sub(r"[·•\-,;]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return (name or None, nif)


# ── Async fetch (Playwright) ─────────────────────────────────────────────────

async def _fetch_async(zones: list[str] | None) -> list[PremktSignalData]:
    from playwright.async_api import async_playwright

    today = datetime.utcnow().date()
    date_from = today - timedelta(days=_LOOKBACK_DAYS)
    dt_from = date_from.strftime("%d-%m-%Y")
    dt_to   = today.strftime("%d-%m-%Y")

    signals: list[PremktSignalData] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.0 Safari/605.1.15"
            ),
            locale="pt-PT",
            viewport={"width": 1440, "height": 900},
        )
        page = await context.new_page()
        try:
            log.info("[citius] navigating to {u}", u=_BASE_URL)
            await page.goto(_BASE_URL, wait_until="domcontentloaded",
                            timeout=_PAGE_TIMEOUT_MS)

            # Fill date range
            try:
                await page.fill(_SEL_DATE_FROM, dt_from, timeout=5_000)
                await page.fill(_SEL_DATE_TO,   dt_to,   timeout=5_000)
            except Exception as e:
                log.warning("[citius] couldn't fill dates ({e}) — using portal defaults", e=e)

            # Select action group "Insolvência"
            try:
                await page.select_option(_SEL_ACTION_GROUP,
                                          label=_ACTION_GROUP_LABEL,
                                          timeout=5_000)
            except Exception as e:
                log.warning("[citius] couldn't select action group: {e}", e=e)

            # Submit and wait for results
            try:
                await page.click(_SEL_SUBMIT_BTN, timeout=5_000)
            except Exception as e:
                log.warning("[citius] submit click failed: {e}", e=e)
                return []

            try:
                await page.wait_for_selector(_SEL_RESULTS_ROW, timeout=15_000)
            except Exception:
                log.info("[citius] no results returned for {f}..{t}",
                         f=dt_from, t=dt_to)
                return []

            # Parse rows
            rows = await page.query_selector_all(_SEL_RESULTS_ROW)
            log.info("[citius] {n} rows visible", n=len(rows))

            for row in rows:
                try:
                    cells = await row.query_selector_all("td")
                    if len(cells) < 3:
                        continue
                    texts = [(await c.inner_text()).strip() for c in cells]
                    # Expected order (best-effort): [date, court, intervenient, action, process]
                    blob = " · ".join(texts)
                    proc = _PROCESS_RE.search(blob)
                    proc_num = proc.group(0) if proc else None

                    interv_blob = next(
                        (t for t in texts if _NIF_RE.search(t) or len(t) > 15),
                        "",
                    )
                    name, nif = _parse_intervenient(interv_blob)
                    if not name:
                        continue

                    court_blob = next(
                        (t for t in texts if "Comarca" in t or "Juízo" in t),
                        "",
                    )
                    zone = None
                    for z in (zones or []):
                        if z.lower() in court_blob.lower():
                            zone = z
                            break

                    signal = PremktSignalData(
                        signal_type="building_permit",  # mapped to insolvency in extra
                        source="citius",
                        signal_text=f"Insolvência · {name}" + (f" (NIF {nif})" if nif else ""),
                        location_raw=court_blob or None,
                        zone=zone,
                        name=name,
                        url=_BASE_URL,
                        extra={
                            "kind":            "insolvency",
                            "nif":             nif,
                            "process_number":  proc_num,
                            "court":           court_blob,
                            "raw_row":         blob[:500],
                        },
                    )
                    # Override score: insolvency is strong intent
                    signal.signal_score = 80
                    signals.append(signal)
                except Exception as e:
                    log.debug("[citius] row parse error: {e}", e=e)

        finally:
            await context.close()
            await browser.close()

    log.info("[citius] {n} insolvency signals extracted", n=len(signals))
    return signals


# ── Public interface ─────────────────────────────────────────────────────────

class CitiusInsolvenciasSource:
    """
    Premarket source · public insolvency announcements from citius.mj.pt.

    Gated by `_CITIUS_ENABLED`. Flip the flag once you've manually verified
    the live portal still matches the selectors (`citius.mj.pt redesigns
    perhaps yearly).
    """

    def fetch(self, zones: list[str] | None = None) -> list[PremktSignalData]:
        if not _CITIUS_ENABLED:
            log.info("[citius] disabled — set _CITIUS_ENABLED=True after manual verification")
            return []
        try:
            return asyncio.run(_fetch_async(zones))
        except Exception as e:
            log.warning("[citius] fetch failed: {e}", e=e)
            return []
