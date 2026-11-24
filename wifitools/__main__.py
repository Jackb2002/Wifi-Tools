"""CLI:  python -m wifitools <command>

  run [--label before|after|...] [--quick]   full sequential benchmark, saves JSON + prints report
  scan                                       just the RF scan + channel recommendation
  report [file]                              re-print report for a saved snapshot (default: latest)
  compare [before.json after.json]           Before/After table (default: latest 'before' vs 'after')
"""
from __future__ import annotations

import argparse
import sys

from . import bench, compare, docsis, report, scan, util


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="wifitools", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true", help="describe each sub-step and command as it runs")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--label", default="run")
    r.add_argument("--quick", action="store_true", help="10 pings, 5 s load tests")
    r.add_argument("--no-throughput", action="store_true")
    r.add_argument("--docsis", metavar="FILE", help="include a pasted Hub signal/log file in the snapshot")
    d = sub.add_parser("docsis", help="grade pasted cable-modem signal + log pages")
    d.add_argument("file", help="text file with the pasted pages ('-' for stdin)")
    sub.add_parser("scan")
    rp = sub.add_parser("report")
    rp.add_argument("file", nargs="?")
    c = sub.add_parser("compare")
    c.add_argument("before", nargs="?")
    c.add_argument("after", nargs="?")
    a = ap.parse_args(argv)
    util.set_verbose(a.verbose)

    if a.cmd == "run":
        snap = bench.run_all(a.label, 10 if a.quick else 30, 5 if a.quick else 10, a.no_throughput)
        if a.docsis:
            snap["docsis"] = docsis.load(a.docsis)
        path = bench.save(snap)
        print("\n" + report.render(snap) + f"\n\nSaved: {path}")
    elif a.cmd == "docsis":
        print(docsis.render(docsis.load(a.file)))
    elif a.cmd == "scan":
        data = scan.collect()
        if data.get("error"):
            return 1
        for band, recs in data["recommend"].items():
            print(band, "->", ", ".join(f"ch{r['channel']} (load {r['overlap_load']})" for r in recs))
    elif a.cmd == "report":
        f = a.file or bench.latest()[-1]
        print(report.render(bench.load(f)))
    elif a.cmd == "compare":
        if a.before and a.after:
            b, af = bench.load(a.before), bench.load(a.after)
        else:
            bs, afs = bench.latest("before"), bench.latest("after")
            if not bs or not afs:
                print("Need runs labelled 'before' and 'after' (python -m wifitools run --label before).")
                return 1
            b, af = bench.load(bs[-1]), bench.load(afs[-1])
        print(compare.render(b, af))
    return 0


if __name__ == "__main__":
    sys.exit(main())
