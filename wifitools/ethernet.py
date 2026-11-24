"""Wired link health: negotiated speed/duplex, error counters, and adapter settings that matter."""
from __future__ import annotations

import json

from .util import ps

# Advanced properties worth surfacing (display names vary by driver; match loosely).
INTERESTING = ("speed", "duplex", "flow control", "energy", "green", "eee", "jumbo", "interrupt moderation")


def _list(raw: str) -> list:
    raw = raw.strip()
    if not raw:
        return []
    d = json.loads(raw)
    return d if isinstance(d, list) else [d]


def adapters() -> list[dict]:
    rows = _list(ps(
        "Get-NetAdapter -Physical | Where-Object { $_.MediaType -eq '802.3' -and $_.Status -eq 'Up' } |"
        " ForEach-Object { $s = Get-NetAdapterStatistics -Name $_.Name;"
        " [pscustomobject]@{name=$_.Name; description=$_.InterfaceDescription; link_mbps=[int]($_.Speed / 1000000);"
        " full_duplex=$_.FullDuplex; rx_errors=$s.ReceivedPacketErrors; rx_discards=$s.ReceivedDiscardedPackets;"
        " tx_errors=$s.OutboundPacketErrors; tx_discards=$s.OutboundDiscardedPackets;"
        " rx_packets=$s.ReceivedUnicastPackets; tx_packets=$s.SentUnicastPackets} } | ConvertTo-Json -Compress"
    ))
    for a in rows:
        props = _list(ps(
            f"Get-NetAdapterAdvancedProperty -Name '{a['name']}' -ErrorAction SilentlyContinue |"
            " Select-Object DisplayName,DisplayValue | ConvertTo-Json -Compress"
        ))
        a["settings"] = {p["DisplayName"]: p["DisplayValue"] for p in props
                         if any(k in p["DisplayName"].lower() for k in INTERESTING)}
    return rows


def collect() -> dict:
    return {"adapters": adapters()}
