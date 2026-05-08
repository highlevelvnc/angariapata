"""
Schedule storage — recurring scrape definitions persisted to JSON.

Each schedule is a small dict the operator can manage from the
dashboard's "Agenda" section under the Motor page. The storage is
intentionally a flat JSON file (not the SQLite DB) — schedules are
operational config, not domain data, and we want them to survive
schema migrations untouched.

Schema
------
``data/schedules.json``::

    [
      {
        "id":          "abc123",
        "name":        "Manhã Lisboa",
        "hour":        8,
        "minute":      0,
        "days":        [0, 1, 2, 3, 4],   # Mon=0..Sun=6
        "sources":     ["olx", "imovirtual"] | null  (null=auto from registry)
        "zones":       ["Lisboa-Estrela"] | null     (null=settings.zones)
        "enabled":     true,
        "created_at":  1715175600.0,
        "last_run_at": null,
      },
      ...
    ]

API
---
* ``list_schedules()`` → list[dict] in display order (created_at asc)
* ``add(name, hour, minute, days, sources, zones)`` → new id
* ``update(sched_id, **patch)`` → bool
* ``delete(sched_id)`` → bool
* ``toggle(sched_id)`` → new enabled state
* ``mark_ran(sched_id)`` → updates last_run_at to now
* ``next_fire_in_seconds(sched)`` → float or None  (display helper)

Idempotent. Atomic writes via tempfile + os.replace.
"""
from __future__ import annotations

import json
import os
import secrets
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

ROOT  = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "schedules.json"

DAY_NAMES_PT = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")
DAY_NAMES_EN = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


# ─── Internals ──────────────────────────────────────────────────────────────

def _read() -> list[dict]:
    if not STORE.exists():
        return []
    try:
        return json.loads(STORE.read_text())
    except Exception:
        return []


def _write(lst: list[dict]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".schedules_", suffix=".json", dir=str(STORE.parent))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(lst, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STORE)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def _new_id() -> str:
    return secrets.token_hex(4)


# ─── Public CRUD ─────────────────────────────────────────────────────────────

def list_schedules() -> list[dict]:
    """Return all schedules ordered by creation time."""
    out = _read()
    out.sort(key=lambda s: s.get("created_at", 0))
    return out


def add(
    *,
    name:      str,
    hour:      int,
    minute:    int,
    days:      list[int],
    sources:   Optional[list[str]] = None,
    zones:     Optional[list[str]] = None,
    enabled:   bool = True,
) -> str:
    """Append a new schedule and return its id."""
    sched = {
        "id":          _new_id(),
        "name":        (name or "Sem nome").strip()[:60],
        "hour":        max(0, min(23, int(hour))),
        "minute":      max(0, min(59, int(minute))),
        "days":        sorted(set(int(d) for d in days if 0 <= int(d) <= 6)) or list(range(7)),
        "sources":     sources or None,
        "zones":       zones or None,
        "enabled":     bool(enabled),
        "created_at":  time.time(),
        "last_run_at": None,
    }
    lst = _read()
    lst.append(sched)
    _write(lst)
    return sched["id"]


def update(sched_id: str, **patch) -> bool:
    """Patch one schedule in place. Unknown keys are ignored."""
    lst = _read()
    for s in lst:
        if s.get("id") == sched_id:
            allowed = {"name", "hour", "minute", "days", "sources", "zones", "enabled"}
            for k, v in patch.items():
                if k in allowed:
                    s[k] = v
            _write(lst)
            return True
    return False


def delete(sched_id: str) -> bool:
    lst = _read()
    new = [s for s in lst if s.get("id") != sched_id]
    if len(new) == len(lst):
        return False
    _write(new)
    return True


def toggle(sched_id: str) -> Optional[bool]:
    """Flip the enabled bit. Returns the new value or None if not found."""
    lst = _read()
    for s in lst:
        if s.get("id") == sched_id:
            s["enabled"] = not bool(s.get("enabled", True))
            _write(lst)
            return s["enabled"]
    return None


def mark_ran(sched_id: str) -> None:
    lst = _read()
    for s in lst:
        if s.get("id") == sched_id:
            s["last_run_at"] = time.time()
            _write(lst)
            return


# ─── Display helpers ────────────────────────────────────────────────────────

def next_fire_at(sched: dict, now: Optional[datetime] = None) -> Optional[datetime]:
    """Return the next datetime this schedule will trigger, or None when
    disabled. ``now`` is overridable for tests."""
    if not sched.get("enabled"):
        return None
    now = now or datetime.now()
    days = sched.get("days") or list(range(7))
    h, m = int(sched["hour"]), int(sched["minute"])

    for off in range(0, 8):                # search up to 7 days ahead
        cand = now + timedelta(days=off)
        if cand.weekday() not in days:
            continue
        cand = cand.replace(hour=h, minute=m, second=0, microsecond=0)
        if off == 0 and cand <= now:
            continue                       # today's slot already passed
        return cand
    return None


def next_fire_in_seconds(sched: dict) -> Optional[float]:
    nxt = next_fire_at(sched)
    if not nxt:
        return None
    return (nxt - datetime.now()).total_seconds()


def days_label(days: list[int], lang: str = "pt") -> str:
    """Compact human label for a day-mask. Examples:
       [0,1,2,3,4]      → "Seg-Sex"
       [0,1,2,3,4,5,6]  → "Todos os dias"
       [5,6]            → "Sáb-Dom"
       [0,2,4]          → "Seg, Qua, Sex"
    """
    names = DAY_NAMES_PT if lang == "pt" else DAY_NAMES_EN
    if not days:
        return "—"
    days = sorted(set(days))
    if days == list(range(7)):
        return "Todos os dias" if lang == "pt" else "Every day"
    if days == [0, 1, 2, 3, 4]:
        return "Seg-Sex" if lang == "pt" else "Mon-Fri"
    if days == [5, 6]:
        return "Sáb-Dom" if lang == "pt" else "Sat-Sun"
    # Detect a contiguous range
    is_contig = all(days[i] - days[i - 1] == 1 for i in range(1, len(days)))
    if is_contig and len(days) >= 3:
        return f"{names[days[0]]}-{names[days[-1]]}"
    return ", ".join(names[d] for d in days)


def sources_label(sched: dict, lang: str = "pt") -> str:
    s = sched.get("sources")
    if not s:
        return "Auto (registry)" if lang == "en" else "Auto (registo)"
    return " · ".join(s)


def zones_label(sched: dict, lang: str = "pt") -> str:
    z = sched.get("zones")
    if not z:
        return "Todas as zonas" if lang == "pt" else "All zones"
    if len(z) > 3:
        return f"{len(z)} zonas" if lang == "pt" else f"{len(z)} zones"
    return " · ".join(z)
