"""Step 1b: scan nearby APs, count congestion per channel, recommend channels."""
from __future__ import annotations

import re
from collections import defaultdict

from .util import band_from_channel, run

# 5 GHz non-DFS channels are the safest picks (DFS can drop clients on radar events).
FIVE_GHZ_NON_DFS = [36, 40, 44, 48, 149, 153, 157, 161, 165]
TWO_GHZ_CLEAN = [1, 6, 11]


def scan_aps() -> list[dict]:
    """Parse `netsh wlan show networks mode=bssid` into one record per BSSID."""
    text = run(["netsh", "wlan", "show", "networks", "mode=bssid"])
    if "location permission" in text.lower():
        raise PermissionError(
            "Windows blocks Wi-Fi scans until Location is on: Settings > Privacy & security > Location "
            "(turn on 'Location services' and 'Let desktop apps access your location')."
        )
    aps, ssid, auth, cur = [], "", "", None
    for line in text.splitlines():
        s = line.strip()
        if m := re.match(r"SSID \d+ : (.*)", s):
            ssid = m.group(1).strip() or "<hidden>"
        elif m := re.match(r"Authentication\s*: (.*)", s):
            auth = m.group(1).strip()
        elif m := re.match(r"BSSID \d+\s*: (.*)", s):
            cur = {"ssid": ssid, "auth": auth, "bssid": m.group(1).strip()}
            aps.append(cur)
        elif cur is not None:
            if m := re.match(r"Signal\s*: (\d+)%", s):
                cur["signal_pct"] = int(m.group(1))
            elif m := re.match(r"Radio type\s*: (.*)", s):
                cur["phy"] = m.group(1).strip()
            elif m := re.match(r"Band\s*: (.*)", s):
                cur["band_hint"] = m.group(1).strip()
            elif m := re.match(r"Channel\s*: (\d+)", s):
                cur["channel"] = int(m.group(1))
    for ap in aps:
        ch = ap.get("channel", 0)
        ap["band"] = band_from_channel(ch, ap.get("band_hint"))
    return [a for a in aps if a.get("channel")]


def _weight(ap: dict) -> float:
    """Strong neighbours hurt more than faint ones."""
    return max(ap.get("signal_pct", 0), 1) / 100


def congestion(aps: list[dict]) -> dict:
    per: dict[str, dict[int, dict]] = defaultdict(lambda: defaultdict(lambda: {"aps": 0, "load": 0.0}))
    for ap in aps:
        slot = per[ap["band"]][ap["channel"]]
        slot["aps"] += 1
        slot["load"] += _weight(ap)
    return {band: dict(chs) for band, chs in per.items()}


def _overlap_load_24(per_ch: dict[int, dict], ch: int) -> float:
    """2.4 GHz channels are 22 MHz wide and 5 MHz apart, so neighbours within +-4 overlap."""
    return sum(v["load"] for c, v in per_ch.items() if abs(c - ch) <= 4)


def recommend(aps: list[dict]) -> dict:
    cong = congestion(aps)
    rec: dict = {}
    c24 = cong.get("2.4 GHz", {})
    if True:
        scored = sorted(TWO_GHZ_CLEAN, key=lambda ch: _overlap_load_24(c24, ch))
        rec["2.4 GHz"] = [
            {"channel": ch, "overlap_load": round(_overlap_load_24(c24, ch), 2)} for ch in scored
        ]
    c5 = cong.get("5 GHz", {})
    scored5 = sorted(FIVE_GHZ_NON_DFS, key=lambda ch: c5.get(ch, {"load": 0})["load"])
    rec["5 GHz"] = [
        {"channel": ch, "overlap_load": round(c5.get(ch, {"load": 0})["load"], 2)} for ch in scored5
    ]
    return rec


def collect() -> dict:
    try:
        aps = scan_aps()
    except PermissionError as e:
        print(f"    ! {e}", flush=True)
        return {"aps": [], "congestion": {}, "recommend": {}, "error": str(e)}
    return {"aps": aps, "congestion": {b: {str(c): v for c, v in d.items()} for b, d in congestion(aps).items()},
            "recommend": recommend(aps)}
