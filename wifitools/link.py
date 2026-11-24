"""Step 1a: active Wi-Fi link details + interface error counters."""
from __future__ import annotations

import re

from .util import pct_to_dbm, ps, run


def _kv_blocks(text: str) -> list[dict[str, str]]:
    """Split `netsh wlan show interfaces` into one dict per adapter."""
    blocks, cur = [], {}
    for line in text.splitlines():
        m = re.match(r"^\s{2,}([^:]+?)\s*:\s*(.*)$", line)
        if not m:
            continue
        k, v = m.group(1).strip(), m.group(2).strip()
        if k == "Name" and cur:
            blocks.append(cur)
            cur = {}
        cur[k] = v
    if cur:
        blocks.append(cur)
    return blocks


def _num(s: str | None) -> float | None:
    m = re.search(r"[\d.]+", s or "")
    return float(m.group()) if m else None


def wifi_links() -> list[dict]:
    out = []
    for b in _kv_blocks(run(["netsh", "wlan", "show", "interfaces"])):
        connected = b.get("State", "").lower() == "connected"
        entry = {
            "interface": b.get("Name"),
            "adapter": b.get("Description"),
            "state": b.get("State"),
            "connected": connected,
        }
        if connected:
            sig = int(_num(b.get("Signal")) or 0)
            entry.update({
                "ssid": b.get("SSID"),
                "bssid": b.get("AP BSSID") or b.get("BSSID"),
                "phy_mode": b.get("Radio type"),
                "band": b.get("Band"),
                "channel": int(_num(b.get("Channel")) or 0),
                "rx_mbps": _num(b.get("Receive rate (Mbps)")),
                "tx_mbps": _num(b.get("Transmit rate (Mbps)")),
                "signal_pct": sig,
                "signal_dbm_est": pct_to_dbm(sig),
                "auth": b.get("Authentication"),
            })
        out.append(entry)
    return out


def adapter_errors() -> list[dict]:
    """Packet error/discard counters per physical adapter that is up."""
    script = (
        "Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | ForEach-Object {"
        " $s = Get-NetAdapterStatistics -Name $_.Name;"
        " [pscustomobject]@{name=$_.Name; link=$_.LinkSpeed; rx_errors=$s.ReceivedPacketErrors;"
        " rx_discards=$s.ReceivedDiscardedPackets; tx_errors=$s.OutboundPacketErrors;"
        " tx_discards=$s.OutboundDiscardedPackets} } | ConvertTo-Json -Compress"
    )
    import json
    raw = ps(script).strip()
    if not raw:
        return []
    data = json.loads(raw)
    return data if isinstance(data, list) else [data]


def collect() -> dict:
    return {"wifi": wifi_links(), "adapters": adapter_errors()}
