"""
Proxy rotation manager.
Phase 1: Works with optional proxy list from .env.
Phase 2: Plug in Brightdata / Oxylabs residential proxy pool.
"""
from __future__ import annotations

import itertools
import random
from typing import Optional

from config.settings import settings
from utils.logger import get_logger

log = get_logger(__name__)


# ─── User-Agent pool ─────────────────────────────────────────────────────────
# 40 real user-agents covering Chrome/Firefox on Windows/Mac/Linux
USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# Consistent Accept headers matching the user-agent type
CHROME_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "pt-PT,pt;q=0.9,en-GB;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
    "Priority": "u=0, i",
}


# ─── Client Hints (Sec-CH-UA family) ─────────────────────────────────────────
# Modern Chrome / Edge ship these by default; portals' bot detection
# (DataDome, Akamai, Cloudflare) compare them against the User-Agent and
# fingerprint requests that look "headless" by their absence. We synthesise
# these from the UA string so the trio (UA, platform, brand-version) stays
# coherent.

import re as _re

def _parse_ua_for_hints(ua: str) -> dict:
    """Build Sec-CH-UA headers consistent with the User-Agent string.

    Returns a dict with at least the basics ('?0' mobile, full-version brand
    list when Chrome/Edge, platform and bitness). Falls back to safe values
    when the UA doesn't match any known browser pattern.
    """
    hints: dict[str, str] = {"Sec-CH-UA-Mobile": "?0"}

    # Platform — from UA tokens
    if "Windows NT 11.0" in ua:
        platform = '"Windows"'
        hints["Sec-CH-UA-Platform-Version"] = '"15.0.0"'
    elif "Windows NT 10.0" in ua:
        platform = '"Windows"'
        hints["Sec-CH-UA-Platform-Version"] = '"10.0.0"'
    elif "Mac OS X 14" in ua or "Macintosh; Intel Mac OS X 14" in ua:
        platform = '"macOS"'
        hints["Sec-CH-UA-Platform-Version"] = '"14.4.0"'
    elif "Mac OS X 13" in ua:
        platform = '"macOS"'
        hints["Sec-CH-UA-Platform-Version"] = '"13.6.0"'
    elif "Mac OS X" in ua or "Macintosh" in ua:
        platform = '"macOS"'
    elif "Linux" in ua and "X11" in ua:
        platform = '"Linux"'
    else:
        platform = '"Unknown"'
    hints["Sec-CH-UA-Platform"] = platform
    hints["Sec-CH-UA-Bitness"] = '"64"'
    hints["Sec-CH-UA-Arch"] = '"arm"' if ("arm" in ua.lower() or "Mac" in ua) else '"x86"'

    # Brand-version trio (Chrome family). Skip for Firefox/Safari — those
    # browsers DO NOT send Sec-CH-UA at all, so its absence is correct
    # signal for them.
    chrome_match = _re.search(r"Chrome/(\d+)", ua)
    edge_match   = _re.search(r"Edg/(\d+)", ua)
    if edge_match and chrome_match:
        v = edge_match.group(1)
        hints["Sec-CH-UA"] = (
            f'"Chromium";v="{chrome_match.group(1)}", '
            f'"Microsoft Edge";v="{v}", "Not.A/Brand";v="24"'
        )
    elif chrome_match and "Firefox" not in ua and "Safari/605" not in ua:
        v = chrome_match.group(1)
        hints["Sec-CH-UA"] = (
            f'"Chromium";v="{v}", "Google Chrome";v="{v}", "Not.A/Brand";v="24"'
        )
        hints["Sec-CH-UA-Full-Version-List"] = (
            f'"Chromium";v="{v}.0.6367.91", '
            f'"Google Chrome";v="{v}.0.6367.91", '
            f'"Not.A/Brand";v="24.0.0.0"'
        )
    return hints


class ProxyManager:
    """
    Manages a rotating pool of HTTP proxies and user-agents.

    Phase 1: Uses proxies from .env PROXY_LIST (can be empty — falls back to direct).
    Phase 2: Replace with residential proxy API (Brightdata, Oxylabs, etc.)
    """

    def __init__(self):
        self._proxies = settings.proxies
        self._proxy_cycle = itertools.cycle(self._proxies) if self._proxies else None
        self._ua_pool = USER_AGENTS.copy()
        random.shuffle(self._ua_pool)
        self._ua_cycle = itertools.cycle(self._ua_pool)
        self._blocked_proxies: set[str] = set()

        if self._proxies:
            log.info("ProxyManager initialised with {n} proxies", n=len(self._proxies))
        else:
            log.info("ProxyManager running without proxies (direct connection)")

    def get_proxy(self) -> Optional[str]:
        """Return the next available proxy URL, or None for direct connection."""
        if not settings.use_proxies or not self._proxy_cycle:
            return None
        # Skip blocked proxies
        for _ in range(len(self._proxies)):
            proxy = next(self._proxy_cycle)
            if proxy not in self._blocked_proxies:
                return proxy
        log.warning("All proxies are blocked — falling back to direct connection")
        return None

    def get_user_agent(self) -> str:
        """Return the next user-agent from the pool."""
        return next(self._ua_cycle)

    def get_headers(self, extra: dict = None, *, host: str = None,
                    persona_index: int = 0) -> dict:
        """Return a complete headers dict.

        When ``host`` is given, headers are derived from a *deterministic
        per-host persona* (same Mac+Chrome returning to OLX every run).
        When ``host`` is None, falls back to the legacy random-UA path.
        """
        if host:
            try:
                from scrapers.anti_block.personas import pick_persona, headers_for
                persona = pick_persona(host, sticky_index=persona_index)
                headers = headers_for(persona)
                if extra:
                    headers.update(extra)
                return headers
            except Exception as e:
                log.debug("[proxy_manager] persona lookup failed: {e}", e=e)

        # Legacy path — random UA + synthesised Client Hints
        ua = self.get_user_agent()
        headers = {**CHROME_HEADERS, "User-Agent": ua}
        headers.update(_parse_ua_for_hints(ua))
        if extra:
            headers.update(extra)
        return headers

    def get_persona_for(self, host: str, persona_index: int = 0):
        """Expose persona to callers that need profile / viewport / locale
        (the http_client factory and the Playwright launcher)."""
        try:
            from scrapers.anti_block.personas import pick_persona
            return pick_persona(host, sticky_index=persona_index)
        except Exception:
            return None

    def mark_blocked(self, proxy: str) -> None:
        """Mark a proxy as blocked so it's skipped temporarily."""
        if proxy:
            self._blocked_proxies.add(proxy)
            log.warning("Proxy marked as blocked: {proxy}", proxy=proxy)

    def get_httpx_kwargs(self) -> dict:
        """Return kwargs dict ready to unpack into httpx.Client(...)."""
        proxy = self.get_proxy()
        kwargs: dict = {"headers": self.get_headers()}
        if proxy:
            kwargs["proxy"] = proxy
        return kwargs
