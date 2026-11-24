"""Parse and grade the cable-modem signal pages you paste from the Hub (Status/Signal + Network Log).

Nothing is fetched from the router: copy the text of the pages into a file and point this at it.
Thresholds are general DOCSIS 3.0 guidance (256 QAM down, 64 QAM ATDMA up), not an ISP guarantee.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter

# Row shapes. Down and Up signal rows share a layout; symbol rate (ksps, >=1000) tells them apart.
_SIG = re.compile(r"^(\d+)\s+(\d{6,})\s+(-?[\d.]+)\s+([\d.]+)\s+(\d+)\s*qam\s+(\d+)$", re.I)
_ERR = re.compile(r"^(\d+)\s+(Locked|Not Locked)\s+([\d.]+)\s+(\d+)\s+(\d+)$", re.I)
_TMO = re.compile(r"^(\d+)\s+(ATDMA|SCDMA|TDMA)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$", re.I)
_LOG = re.compile(r"^(\d\d/\d\d/\d{4})\s+(\d\d:\d\d:\d+)\s+(\w+)\s+(.*)$")
_RATE = re.compile(r"^Max Traffic Rate\s+(\d+)", re.I)

DOWN_POWER_OK = (-7.0, 7.0)   # dBmV
DOWN_SNR_MIN = {256: 33.0, 64: 27.0}   # dB, below this errors are likely
UP_POWER_OK = (35.0, 49.0)    # dBmV, 64 QAM ATDMA
T3_LOG_WARN = 3               # critical ranging timeouts in the pasted log


def parse(text: str) -> dict:
    down, up, errs, tmo, log, rates = [], [], {}, {}, [], []
    for raw in text.splitlines():
        line = raw.strip().replace("\t", " ")
        line = re.sub(r"\s{2,}", " ", line)
        if not line:
            continue
        if m := _SIG.match(line):
            idx, freq, power, a, qam, cid = m.groups()
            if float(a) >= 1000:  # symbol rate => upstream
                up.append({"ch": int(idx), "freq_hz": int(freq), "power_dbmv": float(power),
                           "symbol_ksps": int(float(a)), "qam": int(qam), "id": int(cid)})
            else:
                down.append({"ch": int(idx), "freq_hz": int(freq), "power_dbmv": float(power),
                             "snr_db": float(a), "qam": int(qam), "id": int(cid)})
        elif m := _ERR.match(line):
            errs[int(m.group(1))] = {"locked": m.group(2).lower() == "locked", "rxmer_db": float(m.group(3)),
                                     "pre_rs": int(m.group(4)), "post_rs": int(m.group(5))}
        elif m := _TMO.match(line):
            tmo[int(m.group(1))] = {"t1": int(m.group(3)), "t2": int(m.group(4)),
                                    "t3": int(m.group(5)), "t4": int(m.group(6))}
        elif m := _LOG.match(line):
            log.append({"date": m.group(1), "time": m.group(2), "level": m.group(3).lower(),
                        "msg": m.group(4).split(";")[0].strip()})  # drop MAC-bearing tail
        elif m := _RATE.match(line):
            rates.append(int(m.group(1)))
    for d in down:
        d.update(errs.get(d["ch"], {}))
    for u in up:
        u.update(tmo.get(u["ch"], {}))
    return {"downstream": down, "upstream": up, "log": log,
            "plan_mbps": {"down": round(rates[0] / 1e6, 1), "up": round(rates[1] / 1e6, 1)} if len(rates) >= 2 else None}


def summarize(d: dict) -> dict:
    down, up, log = d["downstream"], d["upstream"], d["log"]
    s: dict = {"plan_mbps": d["plan_mbps"], "down_channels": len(down), "up_channels": len(up)}
    if down:
        p = [c["power_dbmv"] for c in down]
        snr = [c["snr_db"] for c in down]
        s.update(down_power_min=min(p), down_power_max=max(p), down_snr_min=min(snr),
                 down_snr_median=statistics.median(snr),
                 uncorrectable_total=sum(c.get("post_rs", 0) for c in down),
                 correctable_total=sum(c.get("pre_rs", 0) for c in down),
                 down_unlocked=sum(1 for c in down if c.get("locked") is False))
    if up:
        p = [c["power_dbmv"] for c in up]
        s.update(up_power_min=min(p), up_power_max=max(p),
                 t3_counter_total=sum(c.get("t3", 0) for c in up),
                 t4_counter_total=sum(c.get("t4", 0) for c in up))
    t3 = [e for e in log if "t3" in e["msg"].lower() and e["level"] in ("critical", "error")]
    s["t3_log_events"] = len(t3)
    s["t3_log_dates"] = sorted({e["date"] for e in t3}, key=lambda x: (x[6:], x[3:5], x[:2]))
    s["critical_events"] = Counter(e["msg"] for e in log if e["level"] == "critical").most_common(5)
    return s


def findings(d: dict) -> list[tuple[int, str]]:
    s, out = summarize(d), []
    down, up = d["downstream"], d["upstream"]
    lo, hi = DOWN_POWER_OK
    bad = [c["ch"] for c in down if not lo <= c["power_dbmv"] <= hi]
    if bad:
        out.append((8, f"Downstream power out of {lo} to {hi} dBmV on channels {bad}: check coax/splitters."))
    weak = [c["ch"] for c in down if c["snr_db"] < DOWN_SNR_MIN.get(c["qam"], 30)]
    if weak:
        out.append((9, f"Downstream SNR too low for its modulation on channels {weak}: line noise."))
    if s.get("down_unlocked"):
        out.append((9, f"{s['down_unlocked']} downstream channel(s) not locked."))
    unc = s.get("uncorrectable_total", 0)
    if unc > 1000:
        out.append((9, f"{unc} uncorrectable downstream errors: packet loss likely; report to ISP."))
    elif unc > 50:
        out.append((6, f"{unc} uncorrectable downstream errors since boot: watch it, re-check after a day."))
    lo, hi = UP_POWER_OK
    badu = [c["ch"] for c in up if not lo <= c["power_dbmv"] <= hi]
    if badu:
        out.append((9, f"Upstream power outside {lo} to {hi} dBmV on channels {badu}: line/attenuation fault."))
    n = s["t3_log_events"]
    if n >= T3_LOG_WARN:
        out.append((8, f"{n} critical T3 ranging timeouts in the log ({', '.join(s['t3_log_dates'])}): "
                       "intermittent upstream fault; report to ISP and ask for an upstream noise/ingress check."))
    elif n:
        out.append((4, f"{n} T3 ranging timeout(s) in the log: a few are normal; recheck if they recur."))
    if s.get("t3_counter_total", 0) > 20 and not n:
        out.append((5, f"{s['t3_counter_total']} upstream T3 timeouts on the channel counters."))
    if s.get("t4_counter_total", 0):
        out.append((9, f"{s['t4_counter_total']} T4 timeouts: modem may be dropping off the network."))
    return sorted(out, key=lambda x: -x[0])


def render(d: dict) -> str:
    s = summarize(d)
    L = ["## Cable (DOCSIS)"]
    if s["plan_mbps"]:
        L.append(f"- provisioned plan: {s['plan_mbps']['down']} down / {s['plan_mbps']['up']} up Mbps")
    if s["down_channels"]:
        L.append(f"- downstream: {s['down_channels']} ch | power {s['down_power_min']} to {s['down_power_max']} dBmV | "
                 f"SNR min {s['down_snr_min']} / median {s['down_snr_median']} dB")
        L.append(f"- errors since boot: {s['correctable_total']} correctable, {s['uncorrectable_total']} uncorrectable")
    if s["up_channels"]:
        L.append(f"- upstream: {s['up_channels']} ch | power {s['up_power_min']} to {s['up_power_max']} dBmV | "
                 f"T3 counters {s['t3_counter_total']}, T4 {s['t4_counter_total']}")
    L.append(f"- critical T3 events in log: {s['t3_log_events']} {s['t3_log_dates']}")
    L.append("")
    L.append("Cable findings:")
    fs = findings(d)
    L += [f"{i}. [{imp}/10] {msg}" for i, (imp, msg) in enumerate(fs, 1)] or ["- nothing flagged"]
    return "\n".join(L)


def load(path: str) -> dict:
    """Read a pasted-pages file ('-' for stdin) and return parsed data with summary."""
    import sys
    if path == "-":
        text = sys.stdin.read()
    else:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    d = parse(text)
    d["summary"] = summarize(d)
    d["findings"] = findings(d)
    return d
