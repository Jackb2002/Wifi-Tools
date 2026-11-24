# Wifi-Tools

A Windows toolkit that diagnoses your Wi-Fi, Ethernet and cable-modem connection, ranks the real bottlenecks, and compares **before vs after** runs so you can prove a change helped.

Pure Python standard library: no dependencies to install. Uses built-in Windows tools (`netsh`, `ping`, `tracert`, PowerShell).

## Quick start

```powershell
python -m wifitools -v run --label before      # full benchmark, verbose
# ...make a change (DNS, router setting, cable, etc.)...
python -m wifitools -v run --label after
python -m wifitools compare                    # Before vs After table
```

A full run takes a few minutes. Use `--quick` for 10 pings and 5 s load tests.

## What a run measures

Steps run strictly one after another, so idle latency is never polluted by load.

| Step | What it checks |
|---|---|
| **Link** | Wi-Fi PHY mode (11ac/ax/be), band, channel, rates, signal; adapter error counters |
| **Ethernet** | Negotiated speed, duplex, errors, and settings like EEE, Green Ethernet, flow control |
| **RF scan** | Nearby APs per channel, congestion score, best 2.4 GHz (1/6/11) and 5 GHz channels |
| **Context** | Active VPNs, proxy, background traffic, recent Wi-Fi disconnect/roam events |
| **Latency** | 30-ping to gateway and 1.1.1.1 (plus IPv6 if active), jitter, loss, 5-hop traceroute |
| **DNS** | Uncached vs cached lookup time against 1.1.1.1, 8.8.8.8, 9.9.9.9, your router and configured servers |
| **Throughput** | Multi-stream download/upload with latency probed under load: bufferbloat and an RPM-style figure |

The report ends with **ranked findings**, scored by impact and limited to real signals (no placebo OS tweaks).

## Commands

| Command | Purpose |
|---|---|
| `run [--label NAME] [--quick] [--no-throughput] [--docsis FILE]` | Full benchmark; saves JSON to `results/` and prints the report |
| `scan` | Just the RF scan and channel recommendation |
| `report [FILE]` | Re-print the report for a saved run (default: latest) |
| `compare [BEFORE AFTER]` | Before/After table (default: latest `before` vs `after`) |
| `docsis FILE` | Grade pasted cable-modem signal and log pages (see below) |

Add `-v` before any command to describe each step and the commands it runs.

## Cable modem health (`docsis`)

Copy the text of your router's signal-status page and Network Log into a text file, then:

```powershell
python -m wifitools docsis hub.txt
```

It parses downstream/upstream power, SNR, correctable and uncorrectable errors, T3/T4 timeouts and the log, then flags faults such as repeated upstream ranging timeouts. Add `--docsis hub.txt` to `run` to include it in your Before/After comparison. Nothing is fetched from the router, and MAC addresses in the log are dropped.

Thresholds are general DOCSIS 3.0 guidance, not an ISP guarantee. Written against a Virgin Media Hub 3.0's page layout; other modems may need parser tweaks.

## Requirements and gotchas

- **Windows 10/11** and Python 3.10+.
- **Wi-Fi scans need Location on:** Settings > Privacy & security > Location (including desktop apps). The tool tells you if it's blocked.
- **Disconnect your VPN** for a true baseline. The tool flags an active VPN because tunnels inflate every number.
- **Several adapters on one network** (for example Ethernet plus Wi-Fi) means Windows picks one path. To test the radio, disconnect the others.
- **Throughput** uses Cloudflare's speed servers and TCP-connect latency to 1.1.1.1:443. It approximates Apple's `networkQuality` and is not identical to it.

## Privacy

Snapshots in `results/` include nearby network names, BSSIDs, your gateway and DNS servers. The folder is git-ignored, so keep it that way and review a file before sharing it.

## Development

```powershell
python -m unittest discover -s tests -v
```

Layout: one module per step in `wifitools/` (`link`, `ethernet`, `scan`, `latency`, `context`, `dns`, `throughput`, `docsis`), orchestrated by `bench.py`, with `report.py` and `compare.py` for output.

## Ideas for later

- Walk-around signal logger for finding Wi-Fi dead spots
- Continuous monitor that logs drops and latency spikes over time
- Router-specific tuning guides (80/160 MHz width, Wi-Fi 6, SQM)
