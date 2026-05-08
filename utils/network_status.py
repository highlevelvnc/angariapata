"""
Network status — public IP probe + per-portal block detector.

Why
---
The operator runs the dashboard from a mobile-tethered Mac (WOO PT)
sometimes augmented with NordVPN. When the IP gets shadow-banned by
OLX / Imovirtual we want the dashboard to surface that immediately
and tell the operator what to do (rotate VPN server, toggle mobile
data, change Wi-Fi network).

This module exposes two cached probes:

  * ``public_ip()``               → current egress IP + ASN/country.
  * ``portal_block_status()``     → {portal: True/False/None} for OLX
                                    and Imovirtual.

Both results are cached in memory for ``CACHE_TTL_S`` seconds so
calling them on every dashboard render is essentially free.

Probe latency dominates the sub-second budget — so we issue all probes
in parallel via a tiny ThreadPool.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

# Use curl_cffi when present so even the probes look like a real browser.
try:
    from curl_cffi import requests as _requests
    _HAS_CURL = True
except ImportError:                                      # pragma: no cover
    import httpx as _requests
    _HAS_CURL = False


CACHE_TTL_S: float = 60.0
_DEFAULT_TIMEOUT: float = 5.0


@dataclass
class IPInfo:
    ip:      Optional[str]   = None
    country: Optional[str]   = None
    asn:     Optional[str]   = None
    org:     Optional[str]   = None
    fetched_at: float        = field(default_factory=time.time)

    @property
    def is_known_vpn(self) -> bool:
        """Heuristic — NordVPN, Surfshark, ExpressVPN and the datacenter
        providers they rent IPs from."""
        org_lower = (self.org or "").lower()
        return any(kw in org_lower for kw in (
            "nord", "tefincom", "datacamp", "m247", "hostroyale",
            "surfshark", "expressvpn", "private internet access", "pia",
            "cyberghost", "mullvad", "protonvpn", "windscribe",
            "leaseweb", "psychz", "zenlayer", "ovh",
        ))

    @property
    def is_mobile(self) -> bool:
        """Portuguese mobile carriers — WOO, MEO, NOS, Vodafone PT.

        Mobile IPs are typically CGNAT-shared (many users behind one
        public IP), so per-IP rate-limits trigger faster.
        """
        org_lower = (self.org or "").lower()
        return any(kw in org_lower for kw in (
            "vodafone", "woo", "nos comunicacoes", "meo", "altice", "tmn",
        ))


@dataclass
class BlockStatus:
    """Per-portal probe result — True = blocked, False = clean, None = unknown."""
    portal:     str
    blocked:    Optional[bool] = None
    http_code:  Optional[int]  = None
    fetched_at: float          = field(default_factory=time.time)


_ip_cache:     Optional[IPInfo]            = None
_block_cache:  dict[str, BlockStatus]      = {}


def _make_session():
    if _HAS_CURL:
        return _requests.Session(impersonate="chrome131", timeout=_DEFAULT_TIMEOUT)
    return _requests.Client(timeout=_DEFAULT_TIMEOUT, follow_redirects=True, http2=False)


def _now_fresh(ts: float) -> bool:
    return (time.time() - ts) < CACHE_TTL_S


# ── Public IP probe ──────────────────────────────────────────────────────────

def public_ip(force: bool = False) -> IPInfo:
    """Return public IP + country + ASN, cached for 60s.

    Probe chain (each is a separate try/except so any one provider
    going down doesn't blank out the others):
      1. ifconfig.me/ip            → text, just the IP, very reliable
      2. ipwho.is/{ip}              → free JSON, no CF wall, gives org+country
      3. ipinfo.io/{ip}/json        → free JSON fallback (1k req/day)
    """
    import json as _json
    global _ip_cache
    if _ip_cache and not force and _now_fresh(_ip_cache.fetched_at):
        return _ip_cache

    info = IPInfo()
    sess = _make_session()

    # Step 1: get the bare IP — ifconfig.me is the fastest text endpoint.
    try:
        r = sess.get("https://ifconfig.me/ip")
        if r.status_code == 200:
            info.ip = (r.text or "").strip().split()[0]
    except Exception:
        pass
    if not info.ip:
        try:
            r = sess.get("https://api.ipify.org")
            if r.status_code == 200:
                info.ip = (r.text or "").strip().split()[0]
        except Exception:
            pass

    # Step 2: enrich with metadata. Try providers without Cloudflare wall.
    if info.ip:
        for url in (
            f"https://ipwho.is/{info.ip}",
            f"https://ipinfo.io/{info.ip}/json",
        ):
            try:
                r = sess.get(url)
                if r.status_code != 200:
                    continue
                data = _json.loads(r.text)
                # ipwho.is shape
                if data.get("success") is not None or "country" in data:
                    info.country = data.get("country") or info.country
                    info.org     = (
                        (data.get("connection", {}) or {}).get("org")
                        or data.get("org")
                        or data.get("isp")
                    )
                    info.asn     = (data.get("connection", {}) or {}).get("asn") or data.get("asn")
                    break
                # ipinfo.io shape
                if "org" in data or "country" in data:
                    info.country = data.get("country") or info.country
                    info.org     = data.get("org")
                    info.asn     = data.get("asn")
                    break
            except Exception:
                continue

    _ip_cache = info
    return info


# ── Portal block probes ──────────────────────────────────────────────────────

_PORTAL_PROBES: dict[str, str] = {
    # Use the bare /imoveis/ path for both — light, cached on the CDN side,
    # and a 403 there is a strong signal the IP is dirty.
    "olx":        "https://www.olx.pt/imoveis/",
    "imovirtual": "https://www.imovirtual.com/",
}


def _probe_one(portal: str, url: str) -> BlockStatus:
    sess = _make_session()
    try:
        r = sess.get(url)
        return BlockStatus(
            portal=portal,
            blocked=(r.status_code in (403, 429)),
            http_code=r.status_code,
        )
    except Exception:
        return BlockStatus(portal=portal, blocked=None, http_code=None)


def portal_block_status(force: bool = False) -> dict[str, BlockStatus]:
    """Probe every configured portal in parallel; cached for 60s.

    Returns a dict mapping portal-key → BlockStatus.
    """
    global _block_cache
    if (
        _block_cache and not force
        and all(_now_fresh(s.fetched_at) for s in _block_cache.values())
    ):
        return _block_cache

    out: dict[str, BlockStatus] = {}
    with ThreadPoolExecutor(max_workers=len(_PORTAL_PROBES)) as pool:
        futures = {
            pool.submit(_probe_one, k, v): k
            for k, v in _PORTAL_PROBES.items()
        }
        for fut in as_completed(futures):
            res = fut.result()
            out[res.portal] = res

    _block_cache = out
    return out


def overall_status() -> dict:
    """One-shot summary helper for the dashboard widget."""
    ip   = public_ip()
    bps  = portal_block_status()
    blocked = [b.portal for b in bps.values() if b.blocked is True]
    clean   = [b.portal for b in bps.values() if b.blocked is False]
    unknown = [b.portal for b in bps.values() if b.blocked is None]
    return {
        "ip":             ip,
        "by_portal":      bps,
        "blocked_portals": blocked,
        "clean_portals":   clean,
        "unknown_portals": unknown,
        "any_blocked":    bool(blocked),
        "all_clean":      not blocked and not unknown,
    }
