"""Shared helpers: run commands, channel/band maths."""
from __future__ import annotations

import subprocess


VERBOSE = False


def set_verbose(on: bool) -> None:
    global VERBOSE
    VERBOSE = on


def say(msg: str) -> None:
    """Progress line shown only with -v."""
    if VERBOSE:
        print(f"    - {msg}", flush=True)


def run(cmd: list[str] | str, timeout: int = 120) -> str:
    """Run a command and return stdout+stderr as text (never raises on non-zero exit)."""
    shell = isinstance(cmd, str)
    if VERBOSE:
        shown = cmd if shell else (cmd[0] if cmd[0] != "powershell" else "powershell ...") + " " + " ".join(cmd[1:4])
        say(f"running: {shown[:90]}")
    p = subprocess.run(
        cmd, shell=shell, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )
    return (p.stdout or "") + (p.stderr or "")


def ps(script: str, timeout: int = 60) -> str:
    """Run a PowerShell snippet."""
    return run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout)


def band_from_channel(ch: int, hint: str | None = None) -> str:
    """Best-effort band label. 6 GHz channels overlap numbers with 5/2.4, so trust a hint."""
    if hint:
        h = hint.lower()
        if "2.4" in h:
            return "2.4 GHz"
        if "6" in h and "5" not in h:
            return "6 GHz"
        if "5" in h:
            return "5 GHz"
    return "2.4 GHz" if ch <= 14 else "5 GHz"


def pct_to_dbm(pct: int) -> int:
    """Windows reports signal as a 0-100 quality; standard approximation to dBm."""
    return int(pct / 2 - 100)
