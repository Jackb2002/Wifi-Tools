"""Run the full benchmark strictly sequentially and save a timestamped JSON snapshot."""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from . import context, dns, ethernet, latency, link, scan, throughput

RESULTS = Path(__file__).resolve().parent.parent / "results"


def run_all(label: str = "run", ping_count: int = 30, test_seconds: float = 10, skip_throughput: bool = False) -> dict:
    snap: dict = {"label": label, "started": datetime.now().isoformat(timespec="seconds")}

    desc = {
        "link": "reading active Wi-Fi link (PHY, band, channel, rates, signal)",
        "ethernet": "reading wired adapters (negotiated speed, duplex, errors, settings)",
        "scan": "scanning nearby APs and scoring channel congestion",
        "context": "checking VPN/proxy/bandwidth hogs/Wi-Fi drop events",
        "latency": "idle ping (gateway, 1.1.1.1, IPv6 if active) + traceroute",
        "dns": "comparing DNS resolver latency",
        "throughput": "download/upload + bufferbloat under load",
    }

    def step(name: str, fn):
        print(f"[{name}] {desc[name]} ...", flush=True)
        t = time.time()
        snap[name] = fn()
        print(f"[{name}] done in {time.time() - t:.0f}s", flush=True)

    # Order matters: nothing here overlaps, so idle latency is not polluted by load.
    step("link", link.collect)
    step("ethernet", ethernet.collect)
    step("scan", scan.collect)
    step("context", context.collect)
    step("latency", lambda: latency.collect(ping_count))
    step("dns", lambda: dns.collect(snap["latency"].get("gateway")))
    if not skip_throughput:
        step("throughput", lambda: throughput.collect(test_seconds))
    return snap


def save(snap: dict) -> Path:
    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = RESULTS / f"{stamp}-{snap['label']}.json"
    path.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return path


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def latest(label: str | None = None) -> list[Path]:
    files = sorted(RESULTS.glob("*.json"))
    return [f for f in files if label is None or f.stem.endswith(label)]
