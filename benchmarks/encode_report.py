"""B4 report: per-step times, security and sizes from the logs of bench_encode.sh -> markdown tables.
Table 1: c = 2, 4, 8, 16 (results/encode_c*.log). Table 2, if present: c = 16 at the block shape of every
record size of B1 (results/encode_records/, bench_encode.sh records). parse() is also used by comm.py.
Usage: python3 benchmarks/encode_report.py > benchmarks/results/encode.md
"""

import json
import re
from pathlib import Path

RES = Path(__file__).resolve().parent / "results"


def wall_seconds(s):
    """/usr/bin/time wall clock, h:mm:ss or m:ss(.ss) -> seconds."""
    secs = 0.0
    for part in s.split(":"):
        secs = 60 * secs + float(part)
    return secs


def parse(log):
    """Steps (seconds) and parameters of one encoder run from its timestamped log and log.time."""
    lines = [l.split(" ", 1) for l in Path(log).read_text().splitlines()]
    ts = lambda pat: next((float(t) for t, msg in lines if re.search(pat, msg)), None)
    panels = [(float(t), float(re.search(r", ([\d.]+) s$", msg)[1])) for t, msg in lines if "  columns " in msg]
    r_start = panels[0][0] - panels[0][1]                       # panel lines report seconds since compute_r start
    r_end = panels[-1][0]
    find = lambda pat: next(re.search(pat, msg) for _, msg in lines if re.search(pat, msg))
    tm = Path(f"{log}.time").read_text()
    wall = tm.split("Elapsed (wall clock) time (h:mm:ss or m:ss): ")[1].split("\n")[0]
    att = find(r"prange ([\d.]+), mitm ([\d.]+), brute force ([\d.]+)")
    run = {
        "t": int(find(r"t = (\d+) blocks")[1]), "L": int(find(r"L = (\d+) bytes")[1]),
        "m": int(find(r"m = (\d+)")[1]), "s": int(find(r"s = (\d+)$")[1]), "lam": int(find(r"lambda' = (\d+)")[1]),
        "attacks": (att[1], att[2], att[3]),
        "scan": ts("^Database") - ts("^scanning"), "report": ts("^packing") - ts("^Database"),
        "pack": r_start - ts("^packing"), "r": r_end - r_start, "post": ts("^done") - r_end,
        "wall": wall, "wall_s": wall_seconds(wall),
        "rss_gib": int(re.search(r"Maximum resident set size \(kbytes\): (\d+)", tm)[1]) / 2**20,
        "site_bytes": int(tm.splitlines()[-3].split()[0]), "shards": int(tm.splitlines()[-1]),
    }
    if ts("^verifying") is not None:                            # logs from before these lines: post only
        run["r_digest"] = ts("^verifying") - ts("^computing r_digest")
        run["verify"] = ts("^verify: OK") - ts("^verifying")
        run["without_verify_s"] = run["wall_s"] - run["verify"]
    return run


def load_records():
    """{(t, L): run} for the c = 16 runs of bench_encode.sh records."""
    return {(r["t"], r["L"]): r for r in map(parse, sorted((RES / "encode_records").glob("encode_t*_L*.log")))}


def label(B):
    return "1 bit" if B == "1bit" else (f"{B // 1024} KiB" if B >= 1024 else f"{B} B")


def main():
    sec = lambda x: f"{x:.0f} s"
    print("| c | t | m | s | λ' | attack bits prange / mitm / brute force | scan | report + estimate | pack X.bin "
          "| R = XH (all panels) | r_digest + verify + params | total (wall) | peak RAM | R size | shards |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for c in (2, 4, 8, 16):
        r = parse(RES / f"encode_c{c}.log")
        print(f"| {c} | {r['t']} | {r['m']} | {r['s']} | {r['lam']} | {' / '.join(r['attacks'])} "
              f"| {sec(r['scan'])} | {sec(r['report'])} | {sec(r['pack'])} | {sec(r['r'])} | {sec(r['post'])} "
              f"| {r['wall']} | {r['rss_gib']:.1f} GiB | {r['site_bytes'] / 2**30:.1f} GiB | {r['shards']} |")

    records = load_records()
    if not records:
        return
    sizes = {}
    for d in json.loads((RES / "comm_shapes.json").read_text()):
        if d["c"] == 16:
            sizes.setdefault((d["t"], d["L"]), []).append(label(d["B"]))
    print("\nc = 16 at the block shape of each record size of B1 (`bench_encode.sh records`):\n")
    print("| record sizes | t | L (bytes) | m | s | λ' | attack bits prange / mitm / brute force "
          "| scan + report + pack | R = XH (all panels) | r_digest + params | total without verify (wall) "
          "| verify | total (wall) | peak RAM | R size | shards |")
    print("|---" * 16 + "|")
    for (t, L), r in sorted(records.items(), key=lambda kv: -kv[0][0]):
        print(f"| {', '.join(sizes.get((t, L), ['?']))} | {t} | {L} | {r['m']} | {r['s']} | {r['lam']} "
              f"| {' / '.join(r['attacks'])} | {sec(r['scan'] + r['report'] + r['pack'])} | {sec(r['r'])} "
              f"| {sec(r['post'] - r['verify'])} | {sec(r['without_verify_s'])} | {sec(r['verify'])} | {r['wall']} "
              f"| {r['rss_gib']:.1f} GiB | {r['site_bytes'] / 2**30:.1f} GiB | {r['shards']} |")


if __name__ == "__main__":
    main()
