"""Step 2b: things that skew results - VPNs, proxies, bandwidth hogs, Wi-Fi drop events."""
from __future__ import annotations

import json
import time

from .util import ps, say

VPN_PATTERN = r"nord|vpn|wireguard|tun|tap|proton|mullvad|express|surfshark|tailscale|zerotier|openvpn"


def _json(raw: str):
    raw = raw.strip()
    if not raw:
        return []
    data = json.loads(raw)
    return data if isinstance(data, list) else [data]


def vpns() -> list[dict]:
    return _json(ps(
        f"Get-NetAdapter | Where-Object {{ $_.Status -eq 'Up' -and ($_.Name + $_.InterfaceDescription) -match '{VPN_PATTERN}' }}"
        " | Select-Object Name,InterfaceDescription | ConvertTo-Json -Compress"
    ))


def proxy() -> dict:
    raw = ps("Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings' |"
             " Select-Object ProxyEnable,ProxyServer,AutoConfigURL | ConvertTo-Json -Compress")
    return json.loads(raw) if raw.strip() else {}


def bandwidth_hogs(seconds: int = 5, top: int = 8) -> dict:
    """Sample per-process network IO and total adapter throughput over a short window."""
    script = f"""
$a = Get-NetAdapterStatistics | Where-Object {{ $_.ReceivedBytes -gt 0 }}
$p1 = Get-Process | Select-Object Id,Name,@{{n='io';e={{0}}}}
$c1 = (Get-Counter '\\Process(*)\\IO Other Bytes/sec','\\Process(*)\\IO Read Bytes/sec','\\Process(*)\\IO Write Bytes/sec' -ErrorAction SilentlyContinue).CounterSamples
Start-Sleep -Seconds {seconds}
$b = Get-NetAdapterStatistics | Where-Object {{ $_.ReceivedBytes -gt 0 }}
$out = foreach ($x in $b) {{ $y = $a | Where-Object Name -eq $x.Name
  [pscustomobject]@{{name=$x.Name; rx_mbps=[math]::Round((($x.ReceivedBytes-$y.ReceivedBytes)*8/1e6)/{seconds},2);
  tx_mbps=[math]::Round((($x.SentBytes-$y.SentBytes)*8/1e6)/{seconds},2)}} }}
$out | ConvertTo-Json -Compress
"""
    adapters = _json(ps(script, timeout=seconds + 60))
    # Network-heavy processes: count established connections per process (cheap, reliable proxy).
    conns = _json(ps(
        "Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue | Group-Object OwningProcess |"
        " Sort-Object Count -Descending | Select-Object -First %d | ForEach-Object {"
        " [pscustomobject]@{pid=[int]$_.Name; connections=$_.Count;"
        " process=(Get-Process -Id ([int]$_.Name) -ErrorAction SilentlyContinue).ProcessName} }"
        " | ConvertTo-Json -Compress" % top
    ))
    return {"idle_throughput": adapters, "top_connection_owners": conns}


def wifi_events(limit: int = 20) -> list[dict]:
    """Recent connect/disconnect/roam events from the WLAN AutoConfig log."""
    return _json(ps(
        "Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-WLAN-AutoConfig/Operational';"
        " Id=8001,8003,11004,11010,12011} -MaxEvents %d -ErrorAction SilentlyContinue |"
        " Select-Object @{n='time';e={$_.TimeCreated.ToString('s')}},Id,"
        "@{n='msg';e={($_.Message -split \"`n\")[0]}} | ConvertTo-Json -Compress" % limit
    ))


def collect(sample_seconds: int = 5) -> dict:
    t = time.time()
    say("looking for active VPN/tunnel adapters")
    v = vpns()
    say(f"found {len(v)} VPN adapter(s); checking system proxy")
    p = proxy()
    say(f"sampling adapter traffic for {sample_seconds}s to spot background bandwidth use")
    load = bandwidth_hogs(sample_seconds)
    say("reading recent Wi-Fi connect/disconnect/roam events from the event log")
    ev = wifi_events()
    return {"vpns": v, "proxy": p, "load": load, "wifi_events": ev, "elapsed_s": round(time.time() - t, 1)}
