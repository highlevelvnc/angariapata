"""
Per-host persona pool — coherent (UA + TLS profile + viewport + locale)
identities that return to each portal consistently across runs.

Why
---
The previous version random.choice'd a different curl_cffi impersonate
profile and a different User-Agent on every session rotation. That
spreads the per-IP fingerprint across 30+ "different browsers" in the
course of a 2-hour run — a signal that, *in itself*, looks bot-shaped
to fraud teams. Real households cycle through maybe 2-3 devices
day-after-day; one Mac in Safari, the same Mac in Chrome, the spouse's
Windows laptop.

This module models that. We define 6 PERSONAS (combinations of
operating system + browser that are statistically common in PT) and
then, for each host (olx.pt, imovirtual.com, …), pick 3 of them
*deterministically* via hash(host + week-of-year). Within those 3,
we rotate per session — so the portal sees three returning
"devices", week after week, without us ever introducing a new one.

What a Persona binds
--------------------
* User-Agent string
* curl_cffi impersonate profile (TLS / JA3 / HTTP/2 SETTINGS coherent)
* Sec-CH-UA family (matches browser brand + version)
* Viewport (matches the OS's typical preset)
* Locale (pt-PT / pt-BR / en-US)
* Timezone (Europe/Lisbon for all PT-shaped users)
* Cookie-jar slug (cookies stored per persona × host)

Persona names are stable: the same host always sees the same 3
"residents" until ROTATION_PERIOD_DAYS expires (default 7 days), at
which point the pool rotates — like a household rebooting devices or
upgrading a browser.
"""
from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass


ROTATION_PERIOD_DAYS: int = 7


@dataclass(frozen=True)
class Persona:
    """A coherent (OS, browser, version) identity. The fields below
    must agree with each other — never tweak one without re-checking
    the others (e.g. don't ship a Mac UA with Sec-CH-UA-Platform:
    "Windows")."""
    name:        str          # human-readable (used in logs + cookie keys)
    ua:          str
    profile:    str           # curl_cffi impersonate profile
    sec_ch_ua:   str           # full brand-version brand list
    sec_platform: str          # "macOS", "Windows", "Linux"
    sec_mobile:  str           # "?0" desktop, "?1" mobile
    sec_arch:    str           # '"x86"' or '"arm"'
    sec_bitness: str           # '"64"' or '"32"'
    viewport:    tuple[int, int]
    locale:      str
    timezone:    str           # IANA name


# ─── Persona catalogue ─────────────────────────────────────────────────────
# Six identities cover the bulk of real PT consumer browsers (StatCounter
# 2024-2025): macOS Chrome, macOS Safari, Windows Chrome (×2 versions),
# Windows Edge, Mac M-series Chrome (arm), Linux Firefox.
#
# Each row is curated, not generated — the `profile` MUST be supported
# by the installed curl_cffi build (verify with the smoke test below).

PERSONAS: tuple[Persona, ...] = (
    Persona(
        name="mac_chrome_intel",
        ua="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        profile="chrome124",
        sec_ch_ua='"Chromium";v="124", "Google Chrome";v="124", "Not.A/Brand";v="24"',
        sec_platform='"macOS"',
        sec_mobile="?0",
        sec_arch='"x86"',
        sec_bitness='"64"',
        viewport=(1440, 900),
        locale="pt-PT",
        timezone="Europe/Lisbon",
    ),
    Persona(
        name="mac_chrome_arm",
        ua="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        profile="chrome131",
        sec_ch_ua='"Chromium";v="131", "Google Chrome";v="131", "Not.A/Brand";v="24"',
        sec_platform='"macOS"',
        sec_mobile="?0",
        sec_arch='"arm"',
        sec_bitness='"64"',
        viewport=(1512, 982),
        locale="pt-PT",
        timezone="Europe/Lisbon",
    ),
    Persona(
        name="mac_safari",
        ua="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 "
           "(KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
        profile="safari17_0",
        sec_ch_ua="",  # Safari does NOT send Sec-CH-UA
        sec_platform='"macOS"',
        sec_mobile="?0",
        sec_arch='"arm"',
        sec_bitness='"64"',
        viewport=(1440, 900),
        locale="pt-PT",
        timezone="Europe/Lisbon",
    ),
    Persona(
        name="win_chrome",
        ua="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        profile="chrome120",
        sec_ch_ua='"Chromium";v="120", "Google Chrome";v="120", "Not.A/Brand";v="24"',
        sec_platform='"Windows"',
        sec_mobile="?0",
        sec_arch='"x86"',
        sec_bitness='"64"',
        viewport=(1920, 1080),
        locale="pt-PT",
        timezone="Europe/Lisbon",
    ),
    Persona(
        name="win_edge",
        ua="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/101.0.0.0 Safari/537.36 Edg/101.0.0.0",
        profile="edge101",
        sec_ch_ua='"Chromium";v="101", "Microsoft Edge";v="101", "Not.A/Brand";v="24"',
        sec_platform='"Windows"',
        sec_mobile="?0",
        sec_arch='"x86"',
        sec_bitness='"64"',
        viewport=(1536, 864),
        locale="pt-PT",
        timezone="Europe/Lisbon",
    ),
    Persona(
        name="linux_firefox",
        ua="Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
        profile="firefox133",
        sec_ch_ua="",  # Firefox does NOT send Sec-CH-UA
        sec_platform='"Linux"',
        sec_mobile="?0",
        sec_arch='"x86"',
        sec_bitness='"64"',
        viewport=(1920, 1080),
        locale="en-US",
        timezone="Europe/Lisbon",
    ),
)


PERSONAS_BY_NAME: dict[str, Persona] = {p.name: p for p in PERSONAS}


# ─── Deterministic per-host pool ────────────────────────────────────────────

def _week_seed() -> int:
    """A seed that bumps every ROTATION_PERIOD_DAYS days. Drives the
    long-cycle pool rotation so the portal sees a "set of devices that
    upgraded over the weekend" rather than the same six forever."""
    return int(time.time()) // (ROTATION_PERIOD_DAYS * 86_400)


def _pool_for(host: str, size: int = 3) -> list[Persona]:
    """Pick ``size`` distinct personas deterministically from PERSONAS
    using hash(host + week_seed) to drive the choice. Same input →
    same output for the lifetime of the rotation period."""
    seed = f"{host}|{_week_seed()}"
    digest = hashlib.sha256(seed.encode()).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    return rng.sample(list(PERSONAS), k=min(size, len(PERSONAS)))


def pick_persona(host: str, *, sticky_index: int = 0) -> Persona:
    """Return the persona at index ``sticky_index`` from the per-host pool.
    Callers rotate ``sticky_index`` every N zones for within-pool variety
    while keeping the 3-persona set itself stable across runs."""
    pool = _pool_for(host)
    if not pool:
        return PERSONAS[0]
    return pool[sticky_index % len(pool)]


def host_persona_names(host: str) -> list[str]:
    """Convenience for logging — what 3 personas does this host see?"""
    return [p.name for p in _pool_for(host)]


# ─── Header materialisation ─────────────────────────────────────────────────

_BASE_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.7"
    ),
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
    "Priority": "u=0, i",
}


def headers_for(persona: Persona) -> dict:
    """Concrete dict ready to pass to httpx / curl_cffi clients.
    Only includes Sec-CH-UA when the persona's browser actually ships
    those headers (Chrome / Edge — yes; Firefox / Safari — no)."""
    h = dict(_BASE_HEADERS)
    h["User-Agent"]      = persona.ua
    al = "pt-PT,pt;q=0.9,en-GB;q=0.8,en;q=0.7"
    if persona.locale == "en-US":
        al = "en-US,en;q=0.9,pt;q=0.7"
    elif persona.locale == "pt-BR":
        al = "pt-BR,pt;q=0.9,en;q=0.7"
    h["Accept-Language"] = al
    if persona.sec_ch_ua:
        h["Sec-CH-UA"]            = persona.sec_ch_ua
        h["Sec-CH-UA-Mobile"]     = persona.sec_mobile
        h["Sec-CH-UA-Platform"]   = persona.sec_platform
        h["Sec-CH-UA-Arch"]       = persona.sec_arch
        h["Sec-CH-UA-Bitness"]    = persona.sec_bitness
    return h


def cookie_slug(persona: Persona, host: str) -> str:
    """Disk-safe key under which to store this persona×host's cookie jar.
    Keeping per-persona slugs means the curl_cffi profile sees only the
    cookies it dropped — no Chrome cookie ever lands on a Firefox UA."""
    safe_host = host.replace(".", "_").replace(":", "_")
    return f"{safe_host}__{persona.name}"
