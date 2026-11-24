"""Step 4: throughput + bufferbloat. Windows has no `networkQuality`, so we replicate it:
multi-stream download/upload against Cloudflare's speed endpoints while a probe measures
latency under load. Loaded-minus-idle latency is the bufferbloat figure."""
from __future__ import annotations

import socket
import statistics
import threading
import time
import urllib.request

from .util import say

HOST = "speed.cloudflare.com"
DOWN = f"https://{HOST}/__down?bytes={{n}}"
UP = f"https://{HOST}/__up"
UA = {"User-Agent": "wifitools/0.1"}


def tcp_rtt(host: str = "1.1.1.1", port: int = 443, timeout: float = 2.0) -> float | None:
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return (time.perf_counter() - t0) * 1000
    except OSError:
        return None


def _probe(stop: threading.Event, out: list[float]) -> None:
    while not stop.is_set():
        r = tcp_rtt()
        if r is not None:
            out.append(r)
        time.sleep(0.1)


def idle_latency(samples: int = 20) -> dict:
    xs = [r for r in (tcp_rtt() for _ in range(samples)) if r is not None]
    return {"median_ms": round(statistics.median(xs), 1), "max_ms": round(max(xs), 1)} if xs else {}


def _download_worker(stop: threading.Event, counter: list[int], lock: threading.Lock) -> None:
    while not stop.is_set():
        try:
            req = urllib.request.Request(DOWN.format(n=25_000_000), headers=UA)
            with urllib.request.urlopen(req, timeout=10) as r:
                while not stop.is_set():
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    with lock:
                        counter[0] += len(chunk)
        except Exception:
            time.sleep(0.2)


def _upload_worker(stop: threading.Event, counter: list[int], lock: threading.Lock) -> None:
    blob = b"\0" * 2_000_000
    while not stop.is_set():
        try:
            req = urllib.request.Request(UP, data=blob, headers=UA, method="POST")
            with urllib.request.urlopen(req, timeout=15) as r:
                r.read()
            with lock:
                counter[0] += len(blob)
        except Exception:
            time.sleep(0.2)


def _run_phase(worker, streams: int, duration: float) -> dict:
    stop, lock, counter, rtts = threading.Event(), threading.Lock(), [0], []
    threads = [threading.Thread(target=worker, args=(stop, counter, lock), daemon=True) for _ in range(streams)]
    probe = threading.Thread(target=_probe, args=(stop, rtts), daemon=True)
    for t in threads:
        t.start()
    time.sleep(2)  # ramp-up: TCP slow start
    with lock:
        start_bytes = counter[0]
    t0 = time.perf_counter()
    probe.start()
    time.sleep(duration)
    with lock:
        moved = counter[0] - start_bytes
    dt = time.perf_counter() - t0
    stop.set()
    mbps = moved * 8 / dt / 1e6
    res = {"mbps": round(mbps, 1)}
    if rtts:
        res["loaded_median_ms"] = round(statistics.median(rtts), 1)
        res["loaded_p95_ms"] = round(sorted(rtts)[int(0.95 * (len(rtts) - 1))], 1)
        res["probe_samples"] = len(rtts)
    return res


def collect(duration: float = 10, streams: int = 6) -> dict:
    say("measuring idle latency (20 TCP connects to 1.1.1.1:443)")
    idle = idle_latency()
    say(f"download test: {streams} streams for {duration:.0f}s (+2s ramp-up), probing latency under load")
    down = _run_phase(_download_worker, streams, duration)
    say(f"download = {down['mbps']} Mbps; cooling down 2s")
    time.sleep(2)
    say(f"upload test: {max(2, streams // 2)} streams for {duration:.0f}s")
    up = _run_phase(_upload_worker, max(2, streams // 2), duration)
    say(f"upload = {up['mbps']} Mbps")
    base = idle.get("median_ms", 0)
    for phase in (down, up):
        if "loaded_median_ms" in phase:
            phase["bufferbloat_ms"] = round(phase["loaded_median_ms"] - base, 1)
            # RPM-style figure: round trips per minute under load
            phase["rpm"] = round(60000 / phase["loaded_median_ms"]) if phase["loaded_median_ms"] else None
    return {"idle_latency": idle, "download": down, "upload": up,
            "note": "TCP-connect RTT to 1.1.1.1:443 probe; Cloudflare multi-stream test. Not Apple's networkQuality."}
