"""
Persona health — track win-rate per (host × persona) and steer the
pool toward identities that still work.

Why
---
Phase 12 introduced a deterministic 3-persona pool per host so the
portal sees consistent "returning devices". That helps avoid the
"every request is a different browser" tell, but it doesn't help
when one of the three personas catches a 403 streak (e.g. the
Chrome 120 build hits a DataDome rule the others sidestep). Round-
robin sticks with the broken persona for one in three sessions
forever.

This module records every request outcome and biases the persona
picker toward whoever's still getting 200s. Persona that just took
back-to-back 403s gets a 30-minute cooldown; persona that's clearing
99% of requests gets the lion's share of new sessions.

Behaviour
---------
* ``record_outcome(host, persona_name, ok=True/False)`` is called
  from BaseScraper._get on every response. Cheap — appends to an
  in-memory dict + flushes to JSON every 30s.
* ``health_for(host, persona_name)`` returns a snapshot dict.
* ``pick_weighted(host, candidates, sticky_index)`` is the smart
  picker — falls back gracefully when no health data exists yet.
* ``cooldown_remaining(host, persona_name)`` lets the dashboard
  widget surface "this persona is sleeping for N min".

State persists at ``data/persona_health.json`` and rotates weekly
in lockstep with the persona-pool rotation (Phase 12) so we don't
cling to stats from a previous pool.
"""
from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path
from threading import RLock
from typing import Optional


ROOT = Path(__file__).resolve().parent.parent.parent
HEALTH_PATH = ROOT / "data" / "persona_health.json"

# Cooldown windows after consecutive failures.
COOLDOWN_AFTER_BLOCKS:    int   = 3        # block-streak length to trigger
COOLDOWN_DURATION_S:      float = 30 * 60  # 30 minutes silent

# Decay factor — old wins/losses get gradually forgotten so a single
# bad week doesn't haunt a persona forever once the IP cools down.
DECAY_HALF_LIFE_S:        float = 4 * 3600  # 4 hours

# Flush cadence — write the JSON at most this often when call site
# is hot.  We always flush on a successful read though, to keep the
# dashboard snappy.
FLUSH_EVERY_S:            float = 30.0

WEEK_S = 7 * 86_400
_lock = RLock()
_cache: dict[str, dict] = {}
_cache_loaded_at: float = 0.0
_last_flush_at: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# State I/O
# ─────────────────────────────────────────────────────────────────────────────

def _key(host: str, persona_name: str) -> str:
    return f"{host}::{persona_name}"


def _load() -> None:
    """Load JSON state into memory cache. Idempotent — only re-reads
    once per second to avoid hammering the file on a hot loop."""
    global _cache, _cache_loaded_at
    with _lock:
        now = time.time()
        if _cache and (now - _cache_loaded_at) < 1.0:
            return
        if not HEALTH_PATH.exists():
            _cache = {"week_seed": int(now // WEEK_S), "entries": {}}
        else:
            try:
                _cache = json.loads(HEALTH_PATH.read_text())
            except Exception:
                _cache = {"week_seed": int(now // WEEK_S), "entries": {}}
        # Weekly rotation — drop everything if we're in a new pool window
        current_week = int(now // WEEK_S)
        if _cache.get("week_seed") != current_week:
            _cache = {"week_seed": current_week, "entries": {}}
            _save_now(force=True)
        _cache_loaded_at = now


def _save_now(force: bool = False) -> None:
    """Flush in-memory cache to disk. Throttled by FLUSH_EVERY_S
    unless ``force=True``."""
    global _last_flush_at
    with _lock:
        now = time.time()
        if not force and (now - _last_flush_at) < FLUSH_EVERY_S:
            return
        try:
            HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
            HEALTH_PATH.write_text(json.dumps(_cache, ensure_ascii=False, indent=2))
            _last_flush_at = now
        except Exception:
            pass


def _entry(host: str, persona_name: str) -> dict:
    _load()
    k = _key(host, persona_name)
    e = _cache["entries"].get(k)
    if not e:
        e = {
            "ok":              0,
            "blocked":         0,
            "block_streak":    0,
            "last_used":       0.0,
            "last_outcome":    None,
            "cooldown_until":  0.0,
            "last_blocked_at": 0.0,
        }
        _cache["entries"][k] = e
    return e


# ─────────────────────────────────────────────────────────────────────────────
# Recording outcomes
# ─────────────────────────────────────────────────────────────────────────────

def record_outcome(host: str, persona_name: str, ok: bool) -> None:
    """Mark one request outcome. Called from base scraper's _get path.

    Cheap and non-blocking by design — even on a 200-req/zone page we
    only flush every 30s; the in-memory accounting is constant-time.
    """
    if not host or not persona_name:
        return
    with _lock:
        e = _entry(host, persona_name)
        now = time.time()
        e["last_used"]    = now
        if ok:
            e["ok"]            += 1
            e["block_streak"]   = 0
            e["last_outcome"]   = "ok"
        else:
            e["blocked"]       += 1
            e["block_streak"]  += 1
            e["last_outcome"]   = "blocked"
            e["last_blocked_at"] = now
            if e["block_streak"] >= COOLDOWN_AFTER_BLOCKS:
                e["cooldown_until"] = now + COOLDOWN_DURATION_S
        _save_now()


# ─────────────────────────────────────────────────────────────────────────────
# Reading + picking
# ─────────────────────────────────────────────────────────────────────────────

def health_for(host: str, persona_name: str) -> dict:
    """Snapshot — used by the dashboard widget."""
    e = _entry(host, persona_name)
    total = e["ok"] + e["blocked"]
    win_rate = (e["ok"] / total) if total else None
    cooldown = max(0.0, e["cooldown_until"] - time.time())
    return {
        "ok":           e["ok"],
        "blocked":      e["blocked"],
        "total":        total,
        "win_rate":     win_rate,
        "block_streak": e["block_streak"],
        "cooldown_s":   cooldown,
        "last_used":    e["last_used"],
        "last_outcome": e["last_outcome"],
    }


def cooldown_remaining(host: str, persona_name: str) -> float:
    """Seconds until ``persona_name`` can be tried on ``host`` again.
    Zero if not in cooldown."""
    return health_for(host, persona_name)["cooldown_s"]


def _weight(host: str, persona_name: str) -> float:
    """Compute a positive selection weight from the recorded outcomes.

    Empty history → weight 1.0 (uniform). Otherwise: ``win_rate`` over
    the last DECAY_HALF_LIFE_S, clamped to [0.05, 1.0]. Cooldown sets
    the weight to 0.0 — picker will skip this candidate entirely.
    """
    e = _entry(host, persona_name)
    now = time.time()
    if e["cooldown_until"] > now:
        return 0.0
    total = e["ok"] + e["blocked"]
    if total == 0:
        return 1.0
    age = now - e["last_used"]
    decay = math.exp(-age / DECAY_HALF_LIFE_S)
    raw = (e["ok"] / total) * decay + 0.10 * (1 - decay)   # smooth toward 0.10 baseline
    return max(0.05, min(1.0, raw))


def pick_weighted(
    host: str,
    candidates: list[str],
    sticky_index: int = 0,
) -> Optional[str]:
    """Return one of ``candidates`` (persona names) using health-weighted
    sampling. ``sticky_index`` adds a stable tie-breaker so callers that
    rotate per session still get within-pool variety.

    Returns None when every candidate is in cooldown — caller should
    fall back to plain ``candidates[sticky_index % len(candidates)]``.
    """
    if not candidates:
        return None
    weights = [_weight(host, p) for p in candidates]
    if all(w <= 0 for w in weights):
        return None
    rng = random.Random(sticky_index * 1664525 + 1013904223)
    return rng.choices(candidates, weights=weights, k=1)[0]


# ─────────────────────────────────────────────────────────────────────────────
# Reset / inspection
# ─────────────────────────────────────────────────────────────────────────────

def reset_all() -> None:
    """Wipe every recorded outcome — exposed via dashboard if the
    operator wants to start the week's stats fresh."""
    global _cache
    with _lock:
        _cache = {"week_seed": int(time.time() // WEEK_S), "entries": {}}
        _save_now(force=True)


def all_entries() -> dict:
    """Read-only dump of every (host, persona) entry — used by the
    dashboard widget to render the leaderboard."""
    _load()
    return dict(_cache.get("entries", {}))


def force_flush() -> None:
    """Persist immediately — used at scraper shutdown so we don't lose
    the last 30s of outcomes if Streamlit gets killed."""
    _save_now(force=True)
