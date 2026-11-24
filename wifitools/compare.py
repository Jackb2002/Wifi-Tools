"""Before vs After comparison table from two snapshots."""
from __future__ import annotations


def _get(d: dict, path: str):
    for k in path.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


# (label, path, lower_is_better)
METRICS = [
    ("Gateway ping avg (ms)", "latency.ping_gateway.avg_ms", True),
    ("Gateway jitter (ms)", "latency.ping_gateway.jitter_ms", True),
    ("Gateway loss (%)", "latency.ping_gateway.loss_pct", True),
    ("1.1.1.1 ping avg (ms)", "latency.ping_cloudflare.avg_ms", True),
    ("1.1.1.1 jitter (ms)", "latency.ping_cloudflare.jitter_ms", True),
    ("1.1.1.1 loss (%)", "latency.ping_cloudflare.loss_pct", True),
    ("Idle latency (ms)", "throughput.idle_latency.median_ms", True),
    ("Download (Mbps)", "throughput.download.mbps", False),
    ("Download loaded latency (ms)", "throughput.download.loaded_median_ms", True),
    ("Download bufferbloat (ms)", "throughput.download.bufferbloat_ms", True),
    ("Download RPM", "throughput.download.rpm", False),
    ("Upload (Mbps)", "throughput.upload.mbps", False),
    ("Upload loaded latency (ms)", "throughput.upload.loaded_median_ms", True),
    ("Upload bufferbloat (ms)", "throughput.upload.bufferbloat_ms", True),
    ("Upload RPM", "throughput.upload.rpm", False),
    ("Cable T3 events in log", "docsis.summary.t3_log_events", True),
    ("Cable uncorrectable errors", "docsis.summary.uncorrectable_total", True),
    ("Cable upstream T3 counters", "docsis.summary.t3_counter_total", True),
]


def render(before: dict, after: dict) -> str:
    rows = ["| Metric | Before | After | Change |", "|---|---:|---:|---:|"]
    for label, path, lower_better in METRICS:
        b, a = _get(before, path), _get(after, path)
        if b is None or a is None:
            continue
        pct = (a - b) / b * 100 if b else 0
        better = (a < b) if lower_better else (a > b)
        mark = "" if a == b else (" ✅" if better else " ❌")
        rows.append(f"| {label} | {b} | {a} | {pct:+.0f}%{mark} |")
    # DNS: best-of for the resolver that is configured
    for name, s in (("Before", before), ("After", after)):
        cur = s.get("dns", {}).get("system_dns", [])
        rows.append(f"<!-- {name} DNS: {', '.join(cur)} -->")
    return "\n".join(rows)
