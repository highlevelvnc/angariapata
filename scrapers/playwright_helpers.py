"""
Shared Playwright primitives for stealth-required scrapers.

Five scrapers in this codebase use Playwright with a stealth profile —
Idealista, the four bank portals, the Leilões scraper, and Facebook
Marketplace. Until now each duplicated the same browser-launch boilerplate
and stealth init script. That copy/paste was already drifting subtly
between sites (e.g. one had ``hardwareConcurrency`` patches, others
didn't), making bug-for-bug parity impossible.

This module centralises:

  * ``stealth_browser_context()`` — async context manager yielding a
    fully-patched ``BrowserContext``. Caller just opens pages.
  * ``block_heavy_resources(page)`` — abort image/font/CSS/tracking
    requests so listing pages render in ~3-4s instead of 15-30s.
  * ``dismiss_consent_modals(page)`` — sweep the most common cookie
    banner selectors (OneTrust, Didomi, Custom-built).

Designed as drop-in: ``async with stealth_browser_context(headless=...)
as ctx:`` replaces every existing ``async_playwright()`` boilerplate.

Also re-uses ``cookie_jar`` to optionally persist storage_state across
runs — see the ``persist_state_for`` parameter.
"""
from __future__ import annotations

import asyncio
import contextlib
import random
from pathlib import Path
from typing import AsyncIterator, Optional

from utils.logger import get_logger

log = get_logger(__name__)


# Comprehensive stealth init — superset of every per-site patch we had,
# all known DataDome / Incapsula / Cloudflare fingerprint vectors covered.
_STEALTH_INIT_JS = r"""
// 1. webdriver flag
Object.defineProperty(navigator, 'webdriver', {get: () => undefined, configurable: true});

// 2. realistic language list
Object.defineProperty(navigator, 'languages', {
    get: () => ['pt-PT', 'pt', 'en-GB', 'en'],
    configurable: true,
});

// 3. platform
Object.defineProperty(navigator, 'platform', {get: () => 'MacIntel', configurable: true});

// 4. hardware
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8, configurable: true});
Object.defineProperty(navigator, 'deviceMemory',        {get: () => 8, configurable: true});

// 5. window.chrome — present on real Chrome, absent on headless
window.chrome = {
    runtime: {},
    app:     {InstallState: {}, RunningState: {}},
    csi:     () => null,
    loadTimes: () => null,
};

// 6. permissions.query — return real-looking notification permission
const _origQuery = window.navigator.permissions ? window.navigator.permissions.query : null;
if (_origQuery) {
    window.navigator.permissions.query = (params) => (
        params && params.name === 'notifications'
            ? Promise.resolve({state: Notification.permission})
            : _origQuery(params)
    );
}

// 7. plugins length — empty array is the strongest signal of headless
//    Spoofing length=3 with realistic mime types matches default Chrome.
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const fakePlugin = (name, desc, filename) => {
            const p = Object.create(Plugin.prototype);
            Object.defineProperties(p, {
                name:        {get: () => name},
                description: {get: () => desc},
                filename:    {get: () => filename},
                length:      {get: () => 1},
            });
            return p;
        };
        return [
            fakePlugin('PDF Viewer',    'Portable Document Format', 'internal-pdf-viewer'),
            fakePlugin('Chrome PDF Viewer', '', 'mhjfbmdgcfjbbpaeojofohoefgiehjai'),
            fakePlugin('WebKit built-in PDF', '', 'internal-pdf-viewer'),
        ];
    },
    configurable: true,
});

// 8. iframe.contentWindow — DataDome checks if iframes leak headless flag
const origDescriptor = Object.getOwnPropertyDescriptor(
    HTMLIFrameElement.prototype, 'contentWindow'
);
if (origDescriptor && origDescriptor.get) {
    Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
        get: function () {
            const w = origDescriptor.get.call(this);
            try { delete w.navigator.webdriver; } catch (_) {}
            return w;
        },
    });
}

// 9. Function.prototype.toString — must return [native code] for spoofed fns
const origToString = Function.prototype.toString;
Function.prototype.toString = function () {
    if (this === window.navigator.permissions.query) {
        return 'function query() { [native code] }';
    }
    return origToString.apply(this, arguments);
};
"""


# Resource patterns aborted by ``block_heavy_resources`` — cuts ~75% of
# bytes loaded with zero impact on listing data extraction.
_HEAVY_PATTERNS: tuple[str, ...] = (
    "**/*.{png,jpg,jpeg,gif,webp,svg,ico,bmp}",
    "**/*.{woff,woff2,ttf,otf,eot}",
    "**/*.{css,less,scss}",
    "**googletagmanager**",
    "**doubleclick**",
    "**googlesyndication**",
    "**facebook.net**",
    "**connect.facebook.net**",
    "**hotjar.com**",
    "**segment.io**",
    "**amplitude.com**",
    "**newrelic.com**",
    "**sentry.io**",
)


# Common consent-banner selectors — sweep order doesn't matter, the first
# one visible gets clicked. Add new banner variants here as we encounter them.
_CONSENT_SELECTORS: tuple[str, ...] = (
    "#onetrust-accept-btn-handler",
    "button#onetrust-accept-btn-handler",
    "button.onetrust-close-btn-handler",
    "#accept-recommended-btn-handler",
    "button[title='Aceitar Todos os Cookies']",
    "button[title='Accept All Cookies']",
    ".ot-pc-refuse-all-handler",
    "button[id*='accept'][id*='cookie']",
    "button[class*='accept'][class*='cookie']",
    "button[id*='didomi-notice-agree']",
    ".didomi-continue-without-agreeing",
    "#truste-consent-button",
)


# ── Public helpers ───────────────────────────────────────────────────────────

@contextlib.asynccontextmanager
async def stealth_browser_context(
    *,
    headless:           bool          = True,
    user_agent:         Optional[str] = None,
    viewport:           Optional[dict] = None,
    locale:             str           = "pt-PT",
    timezone_id:        str           = "Europe/Lisbon",
    persist_state_for:  Optional[str] = None,
) -> AsyncIterator:
    """
    Async context manager — yields a fully-stealth-patched BrowserContext.

    ``persist_state_for`` (if set) loads a saved storage_state for that
    source slug at entry, and saves it back at exit. Cookies survive
    across runs, dramatically improving anti-bot success rates on second
    and subsequent crawls.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.warning("Playwright not installed — install with `pip install playwright && playwright install chromium`")
        yield None
        return

    from config.zone_config import get_random_user_agent

    ua = user_agent or get_random_user_agent()

    # Real-world viewport mix — sampled from W3C public stats 2024/2025.
    # Sticking to one viewport ("1366x768") across thousands of requests
    # is itself a fingerprint, so we randomise per session.
    _VIEWPORTS: tuple[dict, ...] = (
        {"width": 1920, "height": 1080},  # most common desktop
        {"width": 1536, "height": 864},   # Windows scaled 125%
        {"width": 1440, "height": 900},   # 2nd-most macOS
        {"width": 1366, "height": 768},   # legacy laptop
        {"width": 2560, "height": 1440},  # 1440p monitors
        {"width": 1680, "height": 1050},  # 16:10 monitors
    )
    vp = viewport or random.choice(_VIEWPORTS)

    # Match locale + timezone to a Lisboa-shaped user; vary the locale
    # tail to mimic different browser language preferences.
    _LOCALE_VARIANTS = ("pt-PT", "pt-PT", "pt-PT", "en-US", "pt-BR")
    locale = locale if locale != "pt-PT" else random.choice(_LOCALE_VARIANTS)

    # Optional: load saved storage_state from cookie jar
    storage_state_path = None
    if persist_state_for:
        try:
            from scrapers.anti_block.cookie_jar import load_into_playwright_state
            storage_state_path = load_into_playwright_state(persist_state_for)
            if storage_state_path:
                log.debug("[playwright] loaded saved state for {s}", s=persist_state_for)
        except Exception as e:
            log.debug("[playwright] could not load state: {e}", e=e)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        try:
            context_kwargs = {
                "viewport":     vp,
                "user_agent":   ua,
                "locale":       locale,
                "timezone_id":  timezone_id,
                "extra_http_headers": {"Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8"},
            }
            if storage_state_path:
                context_kwargs["storage_state"] = storage_state_path

            context = await browser.new_context(**context_kwargs)
            await context.add_init_script(_STEALTH_INIT_JS)

            try:
                yield context
            finally:
                # Persist state on exit so the next run inherits cookies
                if persist_state_for:
                    try:
                        from scrapers.anti_block.cookie_jar import save_from_playwright_context
                        await save_from_playwright_context(context, persist_state_for)
                    except Exception as e:
                        log.debug("[playwright] state save failed: {e}", e=e)
                await context.close()
        finally:
            await browser.close()


async def block_heavy_resources(page) -> None:
    """Register network rules that abort image/font/CSS/tracking requests."""
    for pattern in _HEAVY_PATTERNS:
        try:
            await page.route(pattern, lambda route: route.abort())
        except Exception:
            pass


async def dismiss_consent_modals(page, timeout_ms: int = 1500) -> bool:
    """
    Click the first visible consent-banner button. Returns True if any
    button was clicked, False otherwise. Idempotent — safe to call
    repeatedly during a session.
    """
    for sel in _CONSENT_SELECTORS:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click(timeout=timeout_ms)
                await asyncio.sleep(0.3)
                return True
        except Exception:
            continue

    # Final fallback: ESC key dismisses many lightweight modals
    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.15)
    except Exception:
        pass
    return False


async def human_pause(min_s: float = 0.6, max_s: float = 1.6) -> None:
    """Random delay that mimics a human reading the page."""
    await asyncio.sleep(random.uniform(min_s, max_s))


# ── Humanisation helpers — make Playwright look like a tired tab-by-tab
# user, not a deterministic robot. Anti-bot platforms increasingly profile
# pointer telemetry (mousemove samples) and event timing distributions; a
# request that arrives with zero pre-click jitter and pixel-perfect drag
# coordinates is a tell.

def _bezier_path(start: tuple[float, float], end: tuple[float, float],
                 steps: int = 24) -> list[tuple[float, float]]:
    """Cubic-Bézier path between two screen coordinates with two random
    control points that bias the curve away from a straight line."""
    sx, sy = start
    ex, ey = end
    dx, dy = ex - sx, ey - sy
    # Control points displaced perpendicular to the path by ±20% of distance
    perp = (-dy, dx)
    norm = max(1.0, (perp[0] ** 2 + perp[1] ** 2) ** 0.5)
    perp = (perp[0] / norm, perp[1] / norm)
    mag = ((dx * dx + dy * dy) ** 0.5) * random.uniform(0.10, 0.28) * random.choice((-1, 1))
    cx1 = sx + dx * 0.33 + perp[0] * mag
    cy1 = sy + dy * 0.33 + perp[1] * mag
    cx2 = sx + dx * 0.66 + perp[0] * mag * random.uniform(0.4, 1.0)
    cy2 = sy + dy * 0.66 + perp[1] * mag * random.uniform(0.4, 1.0)

    points = []
    for i in range(steps + 1):
        t = i / steps
        # Ease-in-out — humans accelerate then decelerate
        t = t * t * (3 - 2 * t)
        x = (1 - t) ** 3 * sx + 3 * (1 - t) ** 2 * t * cx1 + 3 * (1 - t) * t * t * cx2 + t ** 3 * ex
        y = (1 - t) ** 3 * sy + 3 * (1 - t) ** 2 * t * cy1 + 3 * (1 - t) * t * t * cy2 + t ** 3 * ey
        points.append((x + random.uniform(-0.6, 0.6), y + random.uniform(-0.6, 0.6)))
    return points


async def human_click(page, selector: str, *, timeout_ms: int = 5000) -> bool:
    """Move the cursor along a Bézier path to the element, hover briefly,
    then click. Falls back to a plain click on any failure (e.g. element
    detached) so the caller never blows up on humanisation alone.

    Returns True if the click landed, False otherwise.
    """
    try:
        await page.wait_for_selector(selector, timeout=timeout_ms, state="visible")
        el = await page.query_selector(selector)
        if not el:
            return False
        box = await el.bounding_box()
        if not box:
            await el.click()
            return True

        # Target a random spot inside the element (not dead-centre)
        target_x = box["x"] + box["width"]  * random.uniform(0.30, 0.70)
        target_y = box["y"] + box["height"] * random.uniform(0.30, 0.70)

        # Pretend we were somewhere "above and to the left" before clicking
        start_x  = max(0.0, target_x - random.uniform(120, 320))
        start_y  = max(0.0, target_y - random.uniform(60, 220))

        for x, y in _bezier_path((start_x, start_y), (target_x, target_y),
                                 steps=random.randint(18, 30)):
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.004, 0.018))

        # Brief "hover then commit" — humans hesitate before clicking
        await asyncio.sleep(random.uniform(0.04, 0.18))
        await page.mouse.down()
        await asyncio.sleep(random.uniform(0.04, 0.10))
        await page.mouse.up()
        return True
    except Exception as e:
        # Last resort: fall back to direct click — better a click than no click.
        try:
            await page.click(selector, timeout=timeout_ms)
            return True
        except Exception:
            log.debug("[playwright] human_click {sel} failed: {e}", sel=selector, e=e)
            return False


async def human_scroll(page, *,
                       distance_min: int = 400,
                       distance_max: int = 1400,
                       segments_min: int = 3,
                       segments_max: int = 7) -> None:
    """Scroll down the page in 3-7 small bursts with random pauses between.
    Mimics reading-pause-scroll behaviour. Scrolls upward occasionally
    (like a user re-checking something) about 1 in 5 segments.
    """
    total = random.randint(distance_min, distance_max)
    n_seg = random.randint(segments_min, segments_max)
    seg_size = total // n_seg
    for i in range(n_seg):
        delta = seg_size + random.randint(-40, 40)
        if random.random() < 0.18 and i > 0:
            delta = -int(delta * random.uniform(0.3, 0.6))   # brief scroll-up
        try:
            await page.mouse.wheel(0, delta)
        except Exception:
            try:
                await page.evaluate(f"window.scrollBy(0, {delta})")
            except Exception:
                return
        await asyncio.sleep(random.uniform(0.18, 0.55))
    await asyncio.sleep(random.uniform(0.3, 0.9))


async def human_type(page, selector: str, text: str, *,
                     min_ms: int = 55, max_ms: int = 165,
                     timeout_ms: int = 5000) -> bool:
    """Type into an input one char at a time with realistic per-key delay.
    Adds small clusters of "thinking pauses" every few keys, similar to a
    human composing a search term.
    """
    try:
        await page.wait_for_selector(selector, timeout=timeout_ms)
        await page.click(selector)
        await asyncio.sleep(random.uniform(0.10, 0.25))
        for i, ch in enumerate(text):
            await page.keyboard.type(ch, delay=random.uniform(min_ms, max_ms))
            # Brief thinking pause every 4-7 chars
            if i and i % random.randint(4, 7) == 0:
                await asyncio.sleep(random.uniform(0.10, 0.45))
        return True
    except Exception as e:
        log.debug("[playwright] human_type {sel} failed: {e}", sel=selector, e=e)
        return False
