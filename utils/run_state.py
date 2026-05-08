"""
Run-state — track an in-flight ``main.py run`` subprocess from outside.

Why
---
The "Atualizar dados agora" button used to block the entire Streamlit
thread for tens of minutes (the pipeline runs in-process). The dashboard
froze, page-loads timed out, and the operator could not even open
another tab. That was a UX dealbreaker for a presentation.

This module solves that by running the pipeline as a real OS subprocess
and exposing live status to the dashboard:

  * ``start(sources, zones)``   → fork ``python main.py run …``,
                                  detach, persist PID + log path.
  * ``status()``                → returns RunInfo: alive?, elapsed,
                                  log tail, parsed progress hints.
  * ``stop()``                  → SIGTERM the PID, then SIGKILL after 5s.
  * ``cleanup_stale()``         → garbage-collect stuck state files.

The state lives in ``data/run_state.json`` so it survives Streamlit
re-renders, browser refreshes and even Streamlit restarts. Two
concurrent runs are explicitly rejected — a second click on the
button while the first is still alive is a no-op.

Log files land in ``logs/run_<timestamp>.log``. The dashboard tails
the last ~80 lines plus a count of "Zone 'XYZ' → N listings"
matches for a quick "X/Y zones done, Z listings collected" header.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
STATE_PATH = ROOT / "data" / "run_state.json"


@dataclass
class RunInfo:
    pid:          Optional[int]   = None
    alive:        bool            = False
    started_at:   Optional[float] = None
    elapsed_s:    float           = 0.0
    sources:      list[str]       = None
    zones:        list[str]       = None
    log_path:     Optional[str]   = None
    log_tail:     str             = ""
    zones_done:   int             = 0
    zones_total:  int             = 0
    listings:     int             = 0
    last_zone:    Optional[str]   = None
    blocked_hits: int             = 0
    finished_at:  Optional[float] = None
    finished_ok:  Optional[bool]  = None         # None=running, True/False=done


# ─────────────────────────────────────────────────────────────────────────────
# State file I/O
# ─────────────────────────────────────────────────────────────────────────────

def _read_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def _write_state(d: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2))


def _pid_alive(pid: int) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)        # 0 = "test only", doesn't deliver any signal
        return True
    except OSError:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def is_running() -> bool:
    """Returns True iff a previously-started run is still alive."""
    s = _read_state()
    pid = s.get("pid")
    return bool(pid) and _pid_alive(pid)


def start(sources: list[str] | None = None, zones: list[str] | None = None) -> RunInfo:
    """Fork-and-detach a ``python main.py run`` subprocess.

    If a run is already in flight, this is a no-op (returns existing
    status). The caller should not assume start() always launches.
    """
    if is_running():
        return status()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"run_{ts}.log"

    cmd = [sys.executable, str(ROOT / "main.py"), "run"]
    if sources:
        cmd += ["--sources", ",".join(sources)]
    if zones:
        cmd += ["--zones", ",".join(zones)]

    log_handle = open(log_path, "w")
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        # detach the child so killing Streamlit doesn't take it down
        start_new_session=True,
    )

    state = {
        "pid":         proc.pid,
        "started_at":  time.time(),
        "sources":     sources or [],
        "zones":       zones or [],
        "log_path":    str(log_path),
        "finished_at": None,
        "finished_ok": None,
    }
    _write_state(state)
    return status()


def stop() -> bool:
    """SIGTERM the subprocess, then SIGKILL after a short grace period.
    Returns True iff a process was actually killed."""
    s = _read_state()
    pid = s.get("pid")
    if not pid or not _pid_alive(pid):
        # Mark as finished if state is stale
        if pid:
            s["finished_at"] = time.time()
            s["finished_ok"] = False
            _write_state(s)
        return False
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return False

    # Grace period
    for _ in range(10):
        if not _pid_alive(pid):
            break
        time.sleep(0.5)
    if _pid_alive(pid):
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except OSError:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    s["finished_at"] = time.time()
    s["finished_ok"] = False
    _write_state(s)
    return True


def cleanup_stale() -> None:
    """Drop a state file pointing at a dead PID — used at boot."""
    s = _read_state()
    pid = s.get("pid")
    if pid and not _pid_alive(pid) and not s.get("finished_at"):
        s["finished_at"] = time.time()
        s["finished_ok"] = None
        _write_state(s)


# ─────────────────────────────────────────────────────────────────────────────
# Status + log parsing
# ─────────────────────────────────────────────────────────────────────────────

# Regexes used to parse the structured loguru lines our pipeline emits.
_RE_ZONE_DONE  = re.compile(r"Zone '([^']+)' → (\d+) listings")
_RE_BLOCKED    = re.compile(r"\b(403|429)\b|DataDome block detected|Too Many Requests")
_RE_RUN_HEADER = re.compile(
    r"=== Full pipeline run — sources: (\[[^\]]*\]), zones: (\[[^\]]*\])",
)
_RE_FINISHED   = re.compile(r"Pipeline complete|Run summary|All done|Persisted (\d+) new")


def _tail_text(path: Path, max_lines: int = 80) -> tuple[str, list[str]]:
    """Return (joined-tail, list-of-lines)."""
    try:
        with open(path, "r", errors="replace") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return "", []
    tail = lines[-max_lines:]
    return "".join(tail), lines


def status() -> RunInfo:
    """Snapshot of the current/last run.

    Always cheap — reads the state file + tails the log; never blocks.
    """
    s = _read_state()
    info = RunInfo()
    info.pid          = s.get("pid")
    info.started_at   = s.get("started_at")
    info.sources      = s.get("sources") or []
    info.zones        = s.get("zones")   or []
    info.log_path     = s.get("log_path")
    info.finished_at  = s.get("finished_at")
    info.finished_ok  = s.get("finished_ok")
    info.alive        = bool(info.pid) and _pid_alive(info.pid)
    info.elapsed_s    = (time.time() - (info.started_at or time.time())) if info.started_at else 0

    # Auto-finalise: if the PID is dead but we never got finished_at,
    # mark it finished now — the dashboard should stop showing "running".
    if not info.alive and info.pid and not info.finished_at:
        s["finished_at"] = time.time()
        s["finished_ok"] = None  # we don't know; tail will tell us
        _write_state(s)
        info.finished_at = s["finished_at"]

    if not info.log_path:
        return info
    tail, all_lines = _tail_text(Path(info.log_path), max_lines=80)
    info.log_tail = tail
    if not all_lines:
        return info

    # Pull progress from the *full* log, not just the tail (cheap — these
    # files are <1MB even for full runs).
    full_text = "".join(all_lines)
    info.zones_done   = len(_RE_ZONE_DONE.findall(full_text))
    info.listings     = sum(int(m.group(2)) for m in _RE_ZONE_DONE.finditer(full_text))
    info.blocked_hits = len(_RE_BLOCKED.findall(full_text))
    last = list(_RE_ZONE_DONE.finditer(full_text))
    info.last_zone    = last[-1].group(1) if last else None

    # Total zones — pulled from the run header; fall back to len(zones).
    hdr = _RE_RUN_HEADER.search(full_text)
    if hdr:
        try:
            info.zones_total = full_text.count("Zone '") and len(json.loads(hdr.group(2).replace("'", '"')))
        except Exception:
            info.zones_total = len(info.zones)
    else:
        info.zones_total = len(info.zones)

    if not info.alive and _RE_FINISHED.search(full_text):
        info.finished_ok = True
        if not s.get("finished_ok"):
            s["finished_ok"] = True
            _write_state(s)

    return info
