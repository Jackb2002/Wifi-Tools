"""Step 3: compare uncached DNS latency across resolvers using raw UDP queries (stdlib only)."""
from __future__ import annotations

import random
import socket
import statistics
import string
import struct
import time

from .util import ps, say

POPULAR = ["google.com", "microsoft.com", "amazon.com", "wikipedia.org", "github.com"]


def system_dns_servers() -> list[str]:
    raw = ps("Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object { $_.ServerAddresses } |"
             " ForEach-Object { $_.ServerAddresses } | Select-Object -Unique")
    return [x for x in raw.split() if x]


def _query(server: str, name: str, timeout: float = 2.0) -> float | None:
    """Return round-trip ms for an A query, or None on timeout."""
    tid = random.randrange(65536)
    hdr = struct.pack(">HHHHHH", tid, 0x0100, 1, 0, 0, 0)
    q = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00" + struct.pack(">HH", 1, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        t0 = time.perf_counter()
        s.sendto(hdr + q, (server, 53))
        data, _ = s.recvfrom(2048)
        dt = (time.perf_counter() - t0) * 1000
        return dt if data[:2] == hdr[:2] else None
    except OSError:
        return None
    finally:
        s.close()


def _rand_label() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=12))


def benchmark(server: str, rounds: int = 8) -> dict:
    """Uncached = random label under a real domain (forces recursion; NXDOMAIN is fine).
    Cached = repeat of a popular name (what you hit day to day)."""
    say(f"DNS {server}: {rounds} uncached lookups (random names) + {rounds} cached")
    uncached = [t for t in (_query(server, f"{_rand_label()}.{random.choice(POPULAR)}") for _ in range(rounds)) if t]
    _query(server, POPULAR[0])
    cached = [t for t in (_query(server, POPULAR[0]) for _ in range(rounds)) if t]
    f = lambda xs: round(statistics.median(xs), 1) if xs else None
    return {"server": server, "uncached_ms": f(uncached), "cached_ms": f(cached),
            "timeouts": 2 * rounds - len(uncached) - len(cached)}


def collect(gateway: str | None = None) -> dict:
    current = system_dns_servers()
    targets: dict[str, str] = {"cloudflare": "1.1.1.1", "google": "8.8.8.8", "quad9": "9.9.9.9"}
    if gateway:
        targets["router"] = gateway
    for i, s in enumerate(current):
        if s not in targets.values():
            targets[f"configured_{i}"] = s
    return {"system_dns": current, "results": {label: benchmark(ip) for label, ip in targets.items()}}
