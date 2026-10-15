"""B4 report: per-step times, security and sizes from the logs of bench_encode.sh -> markdown table.
Usage: python3 benchmarks/encode_report.py > benchmarks/results/encode.md
"""

import re
from pathlib import Path

RES = Path(__file__).resolve().parent / "results"

print("| c | t | m | s | λ' | attack bits prange / mitm / brute force | scan | report + estimate | pack X.bin "
      "| R = XH (all panels) | r_digest + verify + params | total (wall) | peak RAM | R size | shards |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for c in (2, 4, 8, 16):
    lines = [l.split(" ", 1) for l in (RES / f"encode_c{c}.log").read_text().splitlines()]
    ts = lambda pat: next(float(t) for t, msg in lines if re.search(pat, msg))
    panels = [(float(t), float(re.search(r", ([\d.]+) s$", msg)[1])) for t, msg in lines if "  columns " in msg]
    r_start = panels[0][0] - panels[0][1]                       # panel lines report seconds since compute_r start
    find = lambda pat: next(re.search(pat, msg) for _, msg in lines if re.search(pat, msg))
    t, m, s = find(r"t = (\d+) blocks")[1], find(r"m = (\d+)")[1], find(r"s = (\d+)$")[1]
    lam = find(r"lambda' = (\d+)")[1]
    att = find(r"prange ([\d.]+), mitm ([\d.]+), brute force ([\d.]+)")
    tm = (RES / f"encode_c{c}.log.time").read_text()
    wall = tm.split("Elapsed (wall clock) time (h:mm:ss or m:ss): ")[1].split("\n")[0]
    rss = int(re.search(r"Maximum resident set size \(kbytes\): (\d+)", tm)[1]) / 2**20
    site_bytes, shards = int(tm.splitlines()[-3].split()[0]), int(tm.splitlines()[-1])
    sec = lambda a, b: f"{b - a:.0f} s"
    print(f"| {c} | {t} | {m} | {s} | {lam} | {att[1]} / {att[2]} / {att[3]} "
          f"| {sec(ts('^scanning'), ts('^Database'))} | {sec(ts('^Database'), ts('^packing'))} "
          f"| {sec(ts('^packing'), r_start)} | {sec(r_start, panels[-1][0])} | {sec(panels[-1][0], ts('^done'))} "
          f"| {wall} | {rss:.1f} GiB | {site_bytes / 2**30:.1f} GiB | {shards} |")
