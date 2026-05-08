"""
HTTP client factory — TLS fingerprint hardening via curl_cffi.

Why this matters
----------------
DataDome, Cloudflare, Akamai and similar anti-bot services don't only
check headers and IP reputation; they also fingerprint the TLS handshake
(JA3 / JA4 hashes) and the HTTP/2 SETTINGS frame. Standard Python clients
(requests, httpx, urllib3) have a JA3 that is *uniquely* Python — every
session of every user of every Python script anywhere on Earth shares it.
The portals know.

curl_cffi wraps `curl-impersonate`, a fork of curl whose TLS stack is a
faithful reimplementation of Chrome / Edge / Safari / Firefox. Requests
through curl_cffi look — at the wire level — like they came out of a
real browser. JA3 changes from the python-canonical
"769,49195-49199-49196-49200-..." fingerprint to one that the portals'
heuristics class as "human".

Behaviour
---------
* If curl_cffi is importable → use it. Sessions cycle through 5 modern
  browser impersonation profiles (Chrome 124, Chrome 120, Edge 122,
  Safari 17.2, Firefox 133) at random per-session, so the JA3 also
  varies between runs.
* If curl_cffi is unavailable → fall back transparently to httpx with
  http/2 off (the next best thing).
* The returned object exposes the subset of the Session API that the
  scrapers actually use (`.get`, `.headers`, `.cookies`, context
  manager). Callers don't need to know which backend they got.
"""
from __future__ import annotations

import random
from typing import Any, Optional

try:
    from curl_cffi import requests as _curl_requests
    _HAVE_CURL_CFFI = True
except ImportError:                                      # pragma: no cover
    _HAVE_CURL_CFFI = False

import httpx

from utils.logger import get_logger

log = get_logger(__name__)


# ── Browser profiles ─────────────────────────────────────────────────────────
# Each is a real (UA, JA3, JA4, HTTP/2 SETTINGS, ALPS) tuple shipped by
# curl-impersonate. We rotate per session so consecutive runs of the same
# scraper don't share the exact same fingerprint.
#
# IMPORTANT: only profiles confirmed-supported by the installed curl_cffi
# build are listed here — see `pip show curl_cffi`. If a profile is added
# upstream, append it; never blind-guess names (the call hard-errors).
_PROFILES: tuple[str, ...] = (
    "chrome131",
    "chrome124",
    "chrome120",
    "edge101",
    "safari17_0",
    "firefox133",
)


def _pick_profile() -> str:
    return random.choice(_PROFILES)


def have_browser_tls() -> bool:
    """True when curl_cffi is available and we can ship browser TLS."""
    return _HAVE_CURL_CFFI


def build_sync_session(
    *,
    headers:          Optional[dict] = None,
    timeout:          float          = 30.0,
    follow_redirects: bool           = True,
    proxy:            Optional[str]  = None,
    profile:          Optional[str]  = None,    # explicit persona profile
) -> Any:
    """Return a session-like object with the scraper-required subset of the
    Session API. Always backed by browser TLS when curl_cffi is available.

    ``profile`` (e.g. "chrome131", "safari17_0") forces a specific
    impersonation. When omitted, picks one from the rotation pool.
    """
    if _HAVE_CURL_CFFI:
        chosen = profile or _pick_profile()
        log.debug("[http_client] sync session — curl_cffi/{p}", p=chosen)
        sess = _curl_requests.Session(
            headers=headers or {},
            timeout=timeout,
            impersonate=chosen,
        )
        # Apply proxy if requested. curl_cffi uses requests-style 'proxies' dict.
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        # curl_cffi follows redirects by default; expose toggle for parity
        sess.allow_redirects = follow_redirects
        return sess

    log.debug("[http_client] sync session — httpx fallback (no curl_cffi)")
    kwargs: dict = {}
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.Client(
        headers=headers or {},
        timeout=timeout,
        follow_redirects=follow_redirects,
        http2=False,
        **kwargs,
    )


def build_async_session(
    *,
    headers:          Optional[dict] = None,
    timeout:          float          = 20.0,
    follow_redirects: bool           = True,
    limits_max:       int            = 6,
    proxy:            Optional[str]  = None,
) -> Any:
    """Async session — same fallback chain.

    Returns either curl_cffi.requests.AsyncSession or httpx.AsyncClient.
    Both expose `await sess.get(url)` and async context manager protocol.
    """
    if _HAVE_CURL_CFFI:
        profile = _pick_profile()
        log.debug("[http_client] async session — curl_cffi/{p}", p=profile)
        kwargs = {
            "headers": headers or {},
            "timeout": timeout,
            "impersonate": profile,
        }
        if proxy:
            kwargs["proxies"] = {"http": proxy, "https": proxy}
        return _curl_requests.AsyncSession(**kwargs)

    log.debug("[http_client] async session — httpx fallback")
    kwargs: dict = {
        "headers": headers or {},
        "timeout": timeout,
        "follow_redirects": follow_redirects,
        "http2": False,
        "limits": httpx.Limits(
            max_keepalive_connections=limits_max,
            max_connections=limits_max * 2,
        ),
    }
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.AsyncClient(**kwargs)
