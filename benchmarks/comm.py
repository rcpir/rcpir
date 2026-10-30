"""B1: communication (and, once measured, server time) of the RC-PIR vs SimplePIR/DoublePIR for a
1 GiB database. RC-PIR communication is analytic, from the encoder's LPN parameter selection
(Mode A, lambda = 128).

Record-size sweep: 1 GiB of fixed-size records (1 bit, or B bytes); the client wants one record.
RC-PIR packs g records per block (g a power of two, a record never spans two blocks):
L = roundup_8(4 + ceil(g * record bits / 8)) bytes, ell = 8 L, t = N / g with N = 2^33 / record bits;
for each c it takes the g with the smallest total communication. SimplePIR/DoublePIR use the layout
of their own PickParams; their sizes are read from results/bw_sweep/ (./run_simplepir.sh bw-sweep).

Writes results/comm_shapes.json: the RC-PIR shape of every (B, c) of the sweep (the g with the
smallest communication), timed by the server and client benchmarks.
Server times, when present: RC-PIR from results/server_records.jsonl (./run_server.sh records, one
thread, one query), SimplePIR/DoublePIR from results/time_sweep/ (./run_simplepir.sh time-sweep).
Order: comm.py (shapes); run_server.sh records, node bench_client.mjs, run_simplepir.sh bw-sweep,
time-sweep and recover-sweep; comm.py again.
Usage: python3 benchmarks/comm.py > benchmarks/results/comm.md

Optional environment (defaults: the spec's selection and benchmarks/results/):
  RCPIR_LPN=estimator     choose s with the LPN estimator (lpn_estimator.py) instead of lpn.mode_a
  RCPIR_LPN_TARGET=...    with RCPIR_LPN=estimator: lambda_eff (default, the spec's margins) or a number of bits
  RCPIR_RESULTS=DIR       where comm_shapes.json is written and server/client times are read; SimplePIR/DoublePIR
                          results are always read from benchmarks/results/
"""

import functools
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "benchmarks/results"                           # SimplePIR/DoublePIR measurements
OURS = Path(os.environ.get("RCPIR_RESULTS", RESULTS))           # RC-PIR shapes and times
OURS_NAME = os.path.relpath(OURS.resolve(), ROOT / "benchmarks")    # for captions, e.g. "results"
sys.path[:0] = [str(ROOT / "encoder/src"), str(ROOT / "common/src"), str(ROOT / "benchmarks")]
from rcpir_encoder import lpn  # noqa: E402

if os.environ.get("RCPIR_LPN") == "estimator":
    import lpn_estimator  # noqa: E402
    TARGET = os.environ.get("RCPIR_LPN_TARGET", "lambda_eff")
    SELECT = functools.partial(lpn_estimator.mode_estimator, target=TARGET)
    SELECTION = (f"s chosen with the LPN estimator ({lpn_estimator.ESTIMATOR_DIR.name}, lpn_estimator.py): "
                 + ("estimator bits >= lambda' = lambda + log2 Q + ceil(log2 t)" if TARGET == "lambda_eff"
                    else f"estimator bits >= {TARGET} (single LPN instance, no margins for Q and t)")
                 + ", and the spec's MITM and brute-force conditions.")
else:
    SELECT = lpn.mode_a
    SELECTION = None

LOG_N = 33                                      # 1 GiB
DB_BYTES = 2 ** (LOG_N - 3)
CS = (2, 4, 8, 16, 256)
RECORD_SIZES = ("1bit", 64, 256, 1024, 4096, 8192, 16384, 65536)   # bytes or "1bit"; as in run_simplepir.sh
HEADLINE_C = 16


def kib(bits):
    return bits / 8 / 1024


def size(n_bytes):
    for unit, k in (("GiB", 30), ("MiB", 20), ("KiB", 10)):
        if n_bytes >= 2**k:
            v = n_bytes / 2**k
            return f"{v:.0f} {unit}" if v == int(v) else f"{v:.1f} {unit}"
    return f"{n_bytes} B"


def record_bits(B):
    return 1 if B == "1bit" else 8 * B


def label(B):
    return "1 bit" if B == "1bit" else size(B)


def log2(x):
    return x.bit_length() - 1


# ---------- RC-PIR: best packing for a record size ----------

def rc_layouts(B, c):
    """All feasible power-of-two packings g for record size B: (g, Selection)."""
    bits = record_bits(B)
    n_rec = 2**LOG_N // bits
    out = []
    g = 1
    while g <= n_rec:
        L = -(-(4 + -(-g * bits // 8)) // 8) * 8
        try:
            out.append((g, SELECT(128, n_rec // g, 8 * L, c)))
        except lpn.Infeasible:
            pass
        g *= 2
    return out


# ---------- SimplePIR / DoublePIR: their BW test output ----------

def parse_bw(path):
    """l, m, Ne and the three sizes (KiB, as printed by their GetBW, truncated) from a BW test log."""
    if not path.exists():
        return None
    txt = path.read_text()
    dims = re.search(r"l=(\d+), m=(\d+)\); logq=(\d+); p=(\d+)", txt)
    ne = re.search(r"number of DB elems per entry is (\d+)", txt)
    kb = {k: int(re.search(rf"{k}: (\d+) KB", txt).group(1))
          for k in ("Offline download", "Online upload", "Online download")}
    packed = re.search(r"Total packed DB size is ~([\d.]+) MB", txt)
    packing = int(re.search(r"packing factor is (\d+)", txt).group(1))
    l, m = int(dims.group(1)), int(dims.group(2))
    return {"l": l, "m": m, "p": int(dims.group(4)), "ne": int(ne.group(1)), "packing": packing,
            "packed_mb": float(packed.group(1)),
            "hint_kib": kb["Offline download"], "up_kib": kb["Online upload"], "down_kib": kb["Online download"]}


def theirs(scheme, B):
    return parse_bw(RESULTS / f"bw_sweep/{scheme}pir_B{B}.txt")


def go_ms(d):
    """Go duration string (e.g. 1m2.5s, 54.6ms, 812µs) -> ms."""
    units = {"h": 3.6e6, "m": 6e4, "s": 1e3, "ms": 1.0, "µs": 1e-3, "us": 1e-3, "ns": 1e-6}
    return sum(float(v) * units[u] for v, u in re.findall(r"([\d.]+)(h|ms|µs|us|ns|m|s)", d))


def their_time(scheme, B):
    """Answer times (ms) of their *PirSingle benchmark: the 5 'Answering query' phases."""
    path = RESULTS / f"time_sweep/{scheme}pir_B{B}.txt"
    if not path.exists():
        return None
    ts = [go_ms(d) for d in re.findall(r"Answering query\.\.\.\n(?:.*\n)*?\tElapsed: (\S+)", path.read_text())]
    return ts or None


def their_query_build(scheme, B):
    """Mean client query-building time (ms) of their *PirSingle benchmark (the 5 'Building query' phases)."""
    path = RESULTS / f"time_sweep/{scheme}pir_B{B}.txt"
    if not path.exists():
        return None
    ts = [go_ms(d) for d in re.findall(r"Building query\.\.\.\n\tElapsed: (\S+)", path.read_text())]
    return sum(ts) / len(ts) if ts else None


def their_decode(scheme, B):
    """Mean decode (Recover) time (ms) from RunPIR runs with the real hint (results/recover_sweep/)."""
    path = RESULTS / f"recover_sweep/{scheme}pir_B{B}.txt"
    if not path.exists():
        return None
    ts = [go_ms(d) for d in re.findall(r"Success!\n\tElapsed: (\S+)", path.read_text())]
    return sum(ts) / len(ts) if ts else None


def load_client_times():
    """RC-PIR client time per query (ms, mean of sample + query + decode) per (B, c), bench_client.mjs records."""
    path = OURS / "client_records.jsonl"
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {(r["B"], r["c"]): r["ms"] for r in rows}


def load_rc_times():
    path = OURS / "server_records.jsonl"
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {(r["t"], r["L"]): r for r in rows if r["threads"] == 1 and r["batch"] == 1}


def fmt_ms(ms):
    return "n/a" if ms is None else f"{ms:.1f} ms"


def fmt_tput(ms):
    """Throughput = 1 GiB of records / mean time, as in SimplePIR."""
    return "n/a" if ms is None else f"{1e3 / ms:.1f} GiB/s"


def their_ms(scheme, B):
    """Mean answer time (ms), None if not measured, or a footnoted note if their run was killed."""
    ts = their_time(scheme, B)
    path = RESULTS / f"time_sweep/{scheme}pir_B{B}.txt"
    if ts is None and path.exists() and "signal: killed" in path.read_text():
        return "killed in Setup¹"
    return mean(ts or [])


def break_even(hint_kib, ours_kib, their_kib):
    """Number of queries up to which RC-PIR (no hint) downloads less in total than the scheme with a hint."""
    if ours_kib <= their_kib:
        return "never"
    return f"{hint_kib / (ours_kib - their_kib):,.0f}"


layouts = {(B, c): rc_layouts(B, c) for B in RECORD_SIZES for c in CS}
best = {k: min(v, key=lambda gs: gs[1].comm.total) for k, v in layouts.items()}
rc_times = load_rc_times()


def rc_ms(sel):
    r = rc_times.get((sel.t, sel.ell // 8))
    return r["ms_mean"] if r else None


def mean(xs):
    return sum(xs) / len(xs) if xs else None


shapes = [{"B": B, "c": c, "g": g, "t": sel.t, "L": sel.ell // 8, "m": sel.m, "s": sel.s}
          for (B, c), (g, sel) in best.items()]
(OURS / "comm_shapes.json").write_text("[\n" + ",\n".join(json.dumps(d) for d in shapes) + "\n]\n")

print(f"n = 2^{LOG_N} bits (1 GiB), lambda = 128, Q = 2^{lpn.LOG2_Q}. Sizes in KiB unless noted.\n")
if SELECTION:
    print(f"LPN parameters: {SELECTION}\n")

# ---- Table 1: headline per record size ----
print(f"## 1. Retrieving one fixed-size record (RC-PIR with c = {HEADLINE_C}, best number of records per block)\n")
print("- Hint: one-time download before the first query (SimplePIR/DoublePIR only).\n"
      "- Online: upload + download of one query; for RC-PIR compute up + down + retrieval up + down.\n"
      "- RC-PIR storage: $R = XH$ on the retrieval server (≈ c × database), written once by the encoder. "
      "Clients never download it, so it does not enter any other column. Besides it, the compute server "
      "holds the database itself, as SimplePIR/DoublePIR servers do.\n"
      "- SimplePIR/DoublePIR sizes: their `GetBW` (`results/bw_sweep/`), layout chosen by their `PickParams`.\n"
      "- Queries until SimplePIR (DoublePIR) is cheaper: after N queries a SimplePIR (DoublePIR) client has "
      "downloaded hint + N × online, an RC-PIR client N × online; RC-PIR's total is smaller up to this many "
      "queries, beyond it the hint has paid for itself: hint / (RC-PIR online − SimplePIR online). "
      "\"never\": RC-PIR is also cheaper per query. Assumptions: each client downloads the hint once and "
      "reuses it for all its queries; the database does not change (after an update SimplePIR/DoublePIR "
      "clients download a new hint, so the count holds per database version); communication only (the "
      "server's time to compute the hint, measured 2.5–2.7 min for SimplePIR at every record size of the sweep "
      "and 2.8 min for DoublePIR with 1-bit entries, and the client's storage for it are not counted); upload and download are added, the hint counts as download.\n"
      "- Server time: one query, one thread, mean (throughput = 1 GiB of records / mean time). SimplePIR/"
      "DoublePIR: the 5 answer times of their `*PirSingle` benchmark (`results/time_sweep/`); RC-PIR: compute "
      f"server, 10 passes on the shape of this row (`{OURS_NAME}/server_records.jsonl`). The retrieval server only "
      "serves static byte ranges and is not timed.\n- Throughput: 1 GiB of records / mean server time, as in SimplePIR.\n")
print("| record size | RC-PIR records per block "
      "| SimplePIR hint | DoublePIR hint | RC-PIR storage "
      "| SimplePIR online | DoublePIR online | RC-PIR online "
      "| queries until SimplePIR is cheaper | queries until DoublePIR is cheaper "
      "| SimplePIR server time | DoublePIR server time | RC-PIR server time "
      "| SimplePIR throughput | DoublePIR throughput | RC-PIR throughput |")
print("|---" * 16 + "|")
for B in RECORD_SIZES:
    g, sel = best[(B, HEADLINE_C)]
    ours = kib(sel.comm.total)
    sp, dp = theirs("simple", B), theirs("double", B)
    hint = [size(th["hint_kib"] * 1024) if th else "n/a" for th in (sp, dp)]
    online = [size((th["up_kib"] + th["down_kib"]) * 1024) if th else "n/a" for th in (sp, dp)]
    be = [break_even(th["hint_kib"], ours, th["up_kib"] + th["down_kib"]) if th else "n/a" for th in (sp, dp)]
    times = [their_ms(sc, B) for sc in ("simple", "double")] + [rc_ms(sel)]
    t_cells = [fmt_ms(t) if not isinstance(t, str) else t for t in times]
    tp_cells = [fmt_tput(t) if not isinstance(t, str) else "–" for t in times]
    print(f"| {label(B)} | {g} | {hint[0]} | {hint[1]} | {size(sel.storage_bits // 8)} "
          f"| {online[0]} | {online[1]} | {size(ours * 1024)} "
          f"| {be[0]} | {be[1]} | " + " | ".join(t_cells) + " | " + " | ".join(tp_cells) + " |")
if any(isinstance(their_ms(sc, B), str) for sc in ("simple", "double") for B in RECORD_SIZES):
    print("\n¹ Killed during their `Setup` with nothing else running (31 GB RAM); the matrix is padded to "
          "57561 × 65536 elements. Most likely out of memory.")

# ---- Table 1b: RC-PIR for every c ----
print("\n## 1b. RC-PIR for every storage factor c: online communication / queries until SimplePIR is cheaper\n")
print("Each cell: RC-PIR online communication per query (best number of records per block for that c), then, "
      "after the slash, the number of queries until SimplePIR is cheaper (as in table 1): "
      "SimplePIR hint / (RC-PIR online − SimplePIR online). \"never\": RC-PIR is also cheaper per query. "
      "Header: c and the retrieval-server storage. SimplePIR's hint and online communication are those of table 1; "
      "DoublePIR is cheaper for no c and record size.\n")
print("| record size | " + " | ".join(f"c = {c} ({c} GiB)" for c in CS) + " |")
print("|---" * (len(CS) + 1) + "|")
for B in RECORD_SIZES:
    sp = theirs("simple", B)
    cells = []
    for c in CS:
        ours = kib(best[(B, c)][1].comm.total)
        be = break_even(sp["hint_kib"], ours, sp["up_kib"] + sp["down_kib"]) if sp else "n/a"
        cells.append(f"{ours:,.0f} KiB / {be}")
    print(f"| {label(B)} | " + " | ".join(cells) + " |")
dp_never = all(break_even(th["hint_kib"], kib(best[(B, c)][1].comm.total), th["up_kib"] + th["down_kib"]) == "never"
               for B in RECORD_SIZES for c in CS if (th := theirs("double", B)))
assert dp_never, "table 1c caption says DoublePIR is cheaper for no c; update it"
notes = []
for c in CS:
    bs = [B for B in RECORD_SIZES if best[(B, c)][0] != best[(B, HEADLINE_C)][0]]
    if bs:
        notes.append(f"c = {c}: " + ", ".join(
            f"{label(B)} ({best[(B, c)][0]} instead of {best[(B, HEADLINE_C)][0]}, server time "
            f"{fmt_ms(rc_ms(best[(B, c)][1]))} instead of {fmt_ms(rc_ms(best[(B, HEADLINE_C)][1]))})" for B in bs))
if notes:
    print(f"\nRecords per block (and so the server time) differ from table 1 (c = {HEADLINE_C}) only for "
          + "; ".join(notes) + ". Otherwise the server times of table 1 hold for every c.")

# ---- Table 1c: runtime for every c ----
client_times = load_client_times()
if rc_times and client_times:
    print("\n## 1c. Runtime per query for every storage factor c (best number of records per block for that c)\n")
    print("- Server time: compute server, one query, one thread (as in table 1; it depends only on the block "
          "shape, not on c). SimplePIR: table 1.\n"
          "- Client time: RC-PIR client in Node, single thread, no network, mean of 100 queries: sample S, build "
          "the compute query (expand s columns of H, XOR), decode (XOR s + 1 blocks). Each configuration runs in "
          f"its own Node process (`bench_client.mjs records`, `{OURS_NAME}/client_records.jsonl`).\n"
          "- SimplePIR/DoublePIR client: their Go client. Query build from the `*PirSingle` logs (mean of 5); "
          "SimplePIR decode = their `Recover` in their full flow `RunPIR` with the real hint, mean of 3 runs, each "
          "run alone (`./run_simplepir.sh recover-sweep`, `results/recover_sweep/`). DoublePIR decode only for "
          "1-bit entries (its hint is 912 MiB to 899 GiB at the other record sizes).\n")
    print("| record size | " + " | ".join(f"server, c = {c}" for c in CS) + " | SimplePIR server "
          "| " + " | ".join(f"client, c = {c}" for c in CS) + " | SimplePIR client (query build + decode) "
          "| DoublePIR client (query build + decode) |")
    print("|---" * (2 * len(CS) + 4) + "|")
    for B in RECORD_SIZES:
        srv = [fmt_ms(rc_ms(best[(B, c)][1])) for c in CS]
        cl = [f"{client_times[(B, c)]['total']['mean']:.1f} ms" if (B, c) in client_times else "n/a" for c in CS]
        sp_srv = their_ms("simple", B)
        clients = []
        for sc in ("simple", "double"):
            qb, dec = their_query_build(sc, B), their_decode(sc, B)
            clients.append(f"{qb + dec:.1f} ms ({qb:.1f} + {dec:.1f})" if qb is not None and dec is not None
                           else ("n/a" if qb is None else fmt_ms(qb) + " + decode n/a"))
        print(f"| {label(B)} | " + " | ".join(srv) + f" | {sp_srv if isinstance(sp_srv, str) else fmt_ms(sp_srv)} | "
              + " | ".join(cl) + f" | {clients[0]} | {clients[1]} |")

# ---- Table 2: their layouts ----
print("\n## 2. SimplePIR/DoublePIR layouts chosen by their `PickParams`\n")
print("Matrix of rows × columns over $\\mathbb{Z}_p$; a record takes Ne (elements per record) consecutive "
      "elements of one column (9–10 bits each), so a column holds rows / Ne records; 1-bit entries are packed "
      "several per element (their packing factor), so a column holds rows × packing. DoublePIR: their `SetupDB` "
      "sets X = Ne, so its hint ($\\delta X n^2$ elements) and download grow linearly with the record size; "
      "for 64 KiB records its "
      "$m \\ge$ `COMP_RATIO`$\\cdot n = 65536$ columns exceed the $2^{14}$ records, so the matrix is padded to 4 GB.\n")
print("| record size | scheme | rows | columns | p | Ne | records per column | packed DB | hint | up | down |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for B in RECORD_SIZES:
    for scheme in ("simple", "double"):
        th = theirs(scheme, B)
        if th is None:
            print(f"| {label(B)} | {scheme.capitalize()}PIR | n/a | | | | | | | | |")
            continue
        print(f"| {label(B)} | {scheme.capitalize()}PIR | {th['l']} | {th['m']} | {th['p']} | {th['ne']} "
              f"| {th['l'] * th['packing'] if th['packing'] else th['l'] // th['ne']} | {th['packed_mb']:.0f} MB "
              f"| {size(th['hint_kib'] * 1024)} "
              f"| {th['up_kib']} | {th['down_kib']} |")

# ---- Table 3: RC-PIR, all c ----
print("\n## 3. RC-PIR by record size and c: best number of records per block vs one record per block\n")
print("t = number of blocks, L = block size (4-byte header + records, rounded up to 8 bytes), "
      "s = blocks fetched from the retrieval server.\n")
print("| record size | c | records per block | t | L (bytes) | s | storage | compute up | compute down "
      "| retrieval up | retrieval down | total | total with one record per block |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for B in RECORD_SIZES:
    for c in CS:
        g, sel = best[(B, c)]
        cm = sel.comm
        g1 = dict(rc_layouts(B, c)).get(1)
        g1_total = f"{kib(g1.comm.total):.1f}" if g1 else "infeasible"
        print(f"| {label(B)} | {c} | {g} | 2^{log2(sel.t)} | {sel.ell // 8} | {sel.s} | {size(sel.storage_bits // 8)} "
              f"| {kib(cm.compute_up):.1f} | {kib(cm.compute_down):.1f} | {kib(cm.retrieval_up):.1f} "
              f"| {kib(cm.retrieval_down):.1f} | {kib(cm.total):.1f} | {g1_total} |")
