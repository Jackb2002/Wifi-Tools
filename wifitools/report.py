"""Turn a snapshot into a readable baseline + ranked findings."""
from __future__ import annotations


def findings(s: dict) -> list[tuple[int, str]]:
    """(impact 1-10, message). Rules are deliberately conservative: only flag real signals."""
    out: list[tuple[int, str]] = []
    ctx, lat, link = s.get("context", {}), s.get("latency", {}), s.get("link", {})
    wifi = [w for w in link.get("wifi", []) if w.get("connected")]

    if ctx.get("vpns"):
        names = ", ".join(v["Name"] for v in ctx["vpns"])
        out.append((9, f"VPN active ({names}): all numbers include tunnel overhead; "
                       "disconnect it for a true Wi-Fi/ISP baseline."))
    if ctx.get("proxy", {}).get("ProxyEnable"):
        out.append((5, "System proxy is enabled and may add latency."))
    wired = s.get("ethernet", {}).get("adapters", [])
    if not wifi and wired:
        out.append((3, "No Wi-Fi link connected: this run measured the wired path only."))
    for e in wired:
        if e.get("link_mbps") and e["link_mbps"] < 1000:
            out.append((9, f"{e['name']} negotiated only {e['link_mbps']} Mbps: bad cable/port or a 100 Mbps switch hop. Reseat/replace cable (Cat5e+)."))
        if e.get("full_duplex") is False:
            out.append((9, f"{e['name']} is half duplex: duplex mismatch, set both ends to auto-negotiate."))
        pk = (e.get("rx_packets") or 0) + (e.get("tx_packets") or 0)
        errs = (e.get("rx_errors") or 0) + (e.get("tx_errors") or 0)
        if errs > 0 and pk and errs / pk > 0.0001:
            out.append((8, f"{e['name']}: {errs} packet errors ({errs / pk:.4%}): suspect cable/connector/port."))
        for k, v in e.get("settings", {}).items():
            if any(x in k.lower() for x in ("energy", "green", "eee")) and str(v).lower() in ("enabled", "on"):
                out.append((3, f"{e['name']}: '{k}' is {v}; disabling can fix random wired latency spikes/drops."))

    for w in wifi:
        if w["signal_pct"] < 60:
            out.append((8, f"Weak signal on {w['interface']}: {w['signal_pct']}% (~{w['signal_dbm_est']} dBm). Move closer/add an AP."))
        if w.get("band") and "2.4" in w["band"]:
            out.append((8, f"Connected on 2.4 GHz ch {w['channel']}: crowded, max ~100-150 Mbps. Prefer 5/6 GHz."))
        if w.get("phy_mode") and any(x in w["phy_mode"] for x in ("802.11n", "802.11g", "802.11a")):
            out.append((7, f"Old PHY mode {w['phy_mode']}: check router for Wi-Fi 5/6 support."))
        if (w.get("tx_mbps") or 0) < 300 and w.get("band") and "2.4" not in w["band"]:
            out.append((5, f"Link rate only {w.get('tx_mbps')} Mbps on {w['band']}: channel width may be 20/40 MHz."))

    for k, label in (("ping_gateway", "Router"), ("ping_cloudflare", "Cloudflare")):
        p = lat.get(k)
        if not p:
            continue
        if p["loss_pct"] > 0:
            out.append((9, f"{label}: {p['loss_pct']}% packet loss."))
        if p.get("jitter_ms", 0) > 8:
            out.append((7, f"{label}: high jitter {p['jitter_ms']} ms."))
    gw = lat.get("ping_gateway", {})
    if gw.get("avg_ms", 0) > 10:
        out.append((7, f"Router latency {gw['avg_ms']} ms is high for a LAN hop: Wi-Fi/RF problem."))

    dns = s.get("dns", {}).get("results", {})
    if dns:
        ranked = sorted((v["uncached_ms"], k) for k, v in dns.items() if v.get("uncached_ms"))
        cur = s["dns"].get("system_dns", [])
        cur_ms = [v["uncached_ms"] for v in dns.values() if v["server"] in cur and v.get("uncached_ms")]
        if ranked and cur_ms and min(cur_ms) > ranked[0][0] * 1.5 + 5:
            out.append((4, f"Fastest DNS is {ranked[0][1]} ({ranked[0][0]} ms) vs your {min(cur_ms)} ms: easy win."))

    tp = s.get("throughput", {})
    for d in ("download", "upload"):
        bb = tp.get(d, {}).get("bufferbloat_ms")
        if bb is not None and bb > 50:
            sev = 8 if bb > 150 else 6
            out.append((sev, f"Bufferbloat on {d}: +{bb} ms under load (RPM {tp[d].get('rpm')}). Enable SQM/fq_codel on router."))

    ap_counts = {}
    for b, chans in s.get("scan", {}).get("congestion", {}).items():
        for ch, v in chans.items():
            ap_counts[(b, ch)] = v["aps"]
    for w in wifi:
        n = ap_counts.get((w["band"], str(w["channel"])), 0)
        if n >= 5:
            out.append((7, f"{n} APs share your channel {w['channel']} ({w['band']}): consider moving."))
    return sorted(out, key=lambda x: -x[0])


def render(s: dict) -> str:
    L = [f"# Wi-Fi diagnostic: {s['label']} ({s['started']})", "", "## Link"]
    for w in s["link"]["wifi"]:
        if w["connected"]:
            L.append(f"- **{w['interface']}** {w['ssid']} | {w['phy_mode']} | {w['band']} ch {w['channel']} | "
                     f"signal {w['signal_pct']}% (~{w['signal_dbm_est']} dBm) | rx/tx {w['rx_mbps']}/{w['tx_mbps']} Mbps")
        else:
            L.append(f"- {w['interface']} ({w['adapter']}): {w['state']}")
    for a in s["link"]["adapters"]:
        L.append(f"- adapter {a['name']} {a['link']}: rx err/discard {a['rx_errors']}/{a['rx_discards']}, "
                 f"tx err/discard {a['tx_errors']}/{a['tx_discards']}")

    for e in s.get("ethernet", {}).get("adapters", []):
        L.append(f"- **{e['name']}** wired {e['link_mbps']} Mbps, full duplex={e['full_duplex']}, "
                 f"errors rx/tx {e['rx_errors']}/{e['tx_errors']}, discards {e['rx_discards']}/{e['tx_discards']}")
        for k, v in e.get("settings", {}).items():
            L.append(f"    - {k}: {v}")

    L += ["", "## Nearby RF"]
    if s["scan"].get("error"):
        L.append(f"- scan unavailable: {s['scan']['error']}")
    for band, chans in s["scan"]["congestion"].items():
        row = ", ".join(f"ch{c}:{v['aps']}" for c, v in sorted(chans.items(), key=lambda x: int(x[0])))
        L.append(f"- {band}: {row}")
    rec = s["scan"]["recommend"]
    for band in ("2.4 GHz", "5 GHz"):
        if band in rec:
            L.append(f"- Best {band} channels: " + ", ".join(str(r["channel"]) for r in rec[band][:3]))

    L += ["", "## Latency (idle)"]
    lat = s["latency"]
    for k in ("ping_gateway", "ping_cloudflare", "ping_cloudflare_v6"):
        p = lat.get(k)
        if p and p.get("ok"):
            L.append(f"- {p['host']}: avg {p['avg_ms']} ms, p95 {p['p95_ms']}, jitter {p['jitter_ms']}, loss {p['loss_pct']}%")
        elif p:
            L.append(f"- {p['host']}: no replies")
    L.append("- traceroute:")
    L += [f"    {h}" for h in lat.get("traceroute", [])]

    L += ["", "## DNS (median ms, uncached / cached)"]
    for label, r in s["dns"]["results"].items():
        L.append(f"- {label} ({r['server']}): {r['uncached_ms']} / {r['cached_ms']}  timeouts {r['timeouts']}")
    L.append(f"- configured: {', '.join(s['dns']['system_dns'])}")

    if "throughput" in s:
        t = s["throughput"]
        L += ["", "## Throughput & bufferbloat",
              f"- idle latency: {t['idle_latency'].get('median_ms')} ms",
              f"- download: {t['download']['mbps']} Mbps | loaded {t['download'].get('loaded_median_ms')} ms | "
              f"bloat +{t['download'].get('bufferbloat_ms')} ms | RPM {t['download'].get('rpm')}",
              f"- upload: {t['upload']['mbps']} Mbps | loaded {t['upload'].get('loaded_median_ms')} ms | "
              f"bloat +{t['upload'].get('bufferbloat_ms')} ms | RPM {t['upload'].get('rpm')}"]

    if "docsis" in s:
        from . import docsis
        L += ["", docsis.render(s["docsis"])]

    L += ["", "## Ranked findings"]
    fs = findings(s)
    L += [f"{i}. [{imp}/10] {msg}" for i, (imp, msg) in enumerate(fs, 1)] or ["- nothing flagged"]
    return "\n".join(L)
