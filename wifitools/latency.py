"""Step 2: idle latency, jitter, loss and a short traceroute."""
from __future__ import annotations

import re
import statistics

from .util import ps, run, say


def default_gateway() -> str | None:
    """Gateway of the lowest-metric non-VPN route (the real LAN router, not the tunnel)."""
    raw = ps(
        "Get-NetRoute -DestinationPrefix 0.0.0.0/0 | Where-Object { $_.NextHop -ne '0.0.0.0' } |"
        " Sort-Object RouteMetric | ForEach-Object { \"$($_.InterfaceAlias)|$($_.NextHop)\" }"
    )
    rows = [r.split("|") for r in raw.split() if "|" in r]
    for alias, hop in rows:
        if not re.search(r"nord|vpn|tun|wireguard|proton|mullvad", alias, re.I):
            return hop
    return rows[0][1] if rows else None


def ping(host: str, count: int = 30, ipv6: bool = False) -> dict:
    say(f"pinging {host} x{count} (takes ~{count}s)")
    cmd = ["ping", "-n", str(count), "-w", "2000"] + (["-6"] if ipv6 else ["-4"]) + [host]
    text = run(cmd, timeout=count * 3 + 10)
    times = [float(m) if m else 0.5 for m in
             (x.group(1) for x in re.finditer(r"time[=<]([\d.]+)ms", text))]
    # "time<1ms" has no number match above for the '<' form with integer; handled by regex too.
    sent = count
    recv = len(times)
    res = {"host": host, "sent": sent, "received": recv,
           "loss_pct": round(100 * (sent - recv) / sent, 1), "ok": recv > 0}
    if times:
        diffs = [abs(a - b) for a, b in zip(times, times[1:])]
        res.update({
            "min_ms": min(times), "avg_ms": round(statistics.mean(times), 2),
            "max_ms": max(times), "p95_ms": round(sorted(times)[int(0.95 * (len(times) - 1))], 2),
            "jitter_ms": round(statistics.mean(diffs), 2) if diffs else 0.0,
        })
    return res


def traceroute(host: str = "1.1.1.1", hops: int = 5) -> list[str]:
    text = run(["tracert", "-d", "-h", str(hops), "-w", "1500", host], timeout=120)
    return [ln.rstrip() for ln in text.splitlines() if re.match(r"\s+\d+\s", ln)]


def has_ipv6() -> bool:
    out = ps("Get-NetIPAddress -AddressFamily IPv6 -PrefixOrigin RouterAdvertisement,Dhcp "
             "-ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike 'fe80*' } | "
             "Select-Object -First 1 -ExpandProperty IPAddress")
    return bool(out.strip())


def collect(count: int = 30) -> dict:
    say("finding default gateway (ignoring VPN tunnel routes)")
    gw = default_gateway()
    say(f"gateway = {gw}")
    say("checking for active IPv6")
    res: dict = {"gateway": gw}
    if gw:
        res["ping_gateway"] = ping(gw, count)
    res["ping_cloudflare"] = ping("1.1.1.1", count)
    if has_ipv6():
        res["ping_cloudflare_v6"] = ping("2606:4700:4700::1111", count, ipv6=True)
    res["traceroute"] = traceroute()
    return res
