"""Analysis of the PQ-EDGELF full re-measurement (option C, 2026-10-16).

Reads the raw run directories produced by orchestrate.sh and derives every quantity
reported in Section 7 except the block structure (fetched separately from the ledger)
and the stand-alone primitive benchmarks (not re-measured).

Usage: python analyze.py <data_dir> <out_dir>
  data_dir: directory containing results/ (local copy of VM1 pqedgelf-rerun-20261016)

Conventions
  * Only directories named runNN are used; *.invalid_* / *.incomplete.* are ignored.
  * Latency and TPS use successful transactions only (status == 0); failures are counted.
  * TPS = successful tx / (last commit - first submission) of the run.
  * Resource samples are restricted to [workload_start_ms, workload_end_ms] of the run.
  * CPU is percent of one core; memory = memory.current - inactive_file (docker-stats
    definition), in MiB.
  * Host I/O = after-minus-before snapshot of wlan0 and mmcblk0 counters, per 1000 sent tx.
"""
import csv
import itertools
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy import stats

DATA = Path(sys.argv[1])
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
RES = DATA / "results"
SCEN = ["S1", "S2", "S3", "S4"]
PAIRS = [("S1", "S2"), ("S3", "S4")]  # (ECDSA, hybrid) with identical endorsement
CONCS = [1, 2, 4, 8, 16]
RUN_RE = re.compile(r"run\d\d")
RNG = np.random.default_rng(20261017)
MIB = 1024 * 1024


# ---------------------------------------------------------------- loaders
def run_dirs(phase, sc, conc):
    base = RES / phase / sc / f"c{conc}"
    return sorted(d for d in base.iterdir() if d.is_dir() and RUN_RE.fullmatch(d.name) and (d / "DONE").exists())


def kv(path):
    out = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def num(d, k):
    try:
        return float(d[k])
    except (KeyError, ValueError):
        return float("nan")


def load_tx(path):
    """Return list of (start_ms, end_ms, latency_ms, status) sorted by start time."""
    rows = []
    with open(path, newline="") as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            rows.append((int(row[3]), int(row[4]), float(row[5]), int(row[6])))
    rows.sort()
    return rows


def tx_metrics(rows, drop=0):
    rows = rows[drop:]
    ok = [x for x in rows if x[3] == 0]
    lat = np.array([x[2] for x in ok])
    span = (max(x[1] for x in ok) - min(x[0] for x in ok)) / 1000.0
    return {
        "sent": len(rows), "ok": len(ok), "fail": len(rows) - len(ok),
        "tps": len(ok) / span, "mean": lat.mean(),
        "p50": np.percentile(lat, 50), "p95": np.percentile(lat, 95), "p99": np.percentile(lat, 99),
    }, lat


SHORT_COLS = ["ts_ms", "cpu_usage_usec", "mem_current", "_memstat", "pids", "peer_rss_kb", "temp_mC", "cpu0_freq_khz", "load1"]


def load_samples(path):
    """pi2 has no memory cgroup controller: its rows have 9 fields (memory.stat missing, memory.current empty)."""
    with open(path, newline="") as f:
        r = csv.reader(f)
        head = next(r)
        rows = []
        for row in r:
            cols = head if len(row) == len(head) else SHORT_COLS
            rows.append({k: float(v) for k, v in zip(cols, row) if v != "" and not k.startswith("_")})
    return rows


def resource_metrics(path, ws, we):
    s = [x for x in load_samples(path) if ws <= x["ts_ms"] <= we]
    if len(s) < 3:
        return None
    t = np.array([x["ts_ms"] for x in s])
    u = np.array([x["cpu_usage_usec"] for x in s])
    rate = np.diff(u) / (np.diff(t) * 1000.0) * 100.0  # percent of one core per interval
    mem = np.array([(x["mem_current"] - x["inactive_file"]) / MIB for x in s if "inactive_file" in x] or [np.nan])
    return {
        "n_samples": len(s),
        "cpu_mean": (u[-1] - u[0]) / ((t[-1] - t[0]) * 1000.0) * 100.0,
        "cpu_peak": rate.max(),
        "mem_mean": mem.mean(), "mem_max": mem.max(),
        "rss_mean_mib": np.mean([x["peer_rss_kb"] / 1024 for x in s if "peer_rss_kb" in x]),
        "temp_max_c": max(x["temp_mC"] for x in s) / 1000.0,
        "freq_min_mhz": min(x["cpu0_freq_khz"] for x in s) / 1000.0,
    }


def ms(a):
    a = np.asarray(a, dtype=float)
    return float(a.mean()), float(a.std(ddof=1)) if len(a) > 1 else 0.0


# ---------------------------------------------------------------- statistics
def hl_shift(a, b):
    """Hodges-Lehmann estimate of the shift b - a."""
    return float(np.median(np.subtract.outer(b, a)))


def cliffs_delta(a, b):
    """P(b > a) - P(b < a)."""
    d = np.subtract.outer(b, a)
    return float((np.sum(d > 0) - np.sum(d < 0)) / d.size)


def exact_perm_mean(a, b):
    pooled = np.concatenate([a, b])
    n = len(a)
    obs = abs(b.mean() - a.mean())
    cnt = tot = 0
    for idx in itertools.combinations(range(len(pooled)), n):
        mask = np.zeros(len(pooled), bool)
        mask[list(idx)] = True
        diff = abs(pooled[~mask].mean() - pooled[mask].mean())
        cnt += diff >= obs - 1e-12
        tot += 1
    return cnt / tot


def bootstrap_hl(a, b, n=10000):
    vals = np.empty(n)
    for i in range(n):
        vals[i] = hl_shift(RNG.choice(a, len(a)), RNG.choice(b, len(b)))
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def compare(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    lo, hi = bootstrap_hl(a, b)
    return {
        "hl": hl_shift(a, b), "ci_lo": lo, "ci_hi": hi,
        "p_u": float(stats.mannwhitneyu(b, a, alternative="two-sided", method="exact").pvalue),
        "p_perm": exact_perm_mean(a, b), "delta": cliffs_delta(a, b),
        "paired_diff_mean": float((b - a).mean()), "paired_diff_min": float((b - a).min()),
        "paired_diff_max": float((b - a).max()),
    }


def write_csv(name, rows):
    if not rows:
        return
    keys = list(rows[0].keys())
    with open(OUT / name, "w", newline="") as f:
        w = csv.DictWriter(f, keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.6g}" if isinstance(v, float) else v) for k, v in r.items()})


summary = {}

# ---------------------------------------------------------------- system benchmark
sys_runs, sys_lat = [], {}
for sc in SCEN:
    lats = []
    for d in run_dirs("system", sc, 1):
        rows = load_tx(d / "invoke_latency.csv")
        m, lat = tx_metrics(rows)
        m50, _ = tx_metrics(rows, drop=50)
        meta = kv(d / "run_meta.txt")
        sys_runs.append({"scenario": sc, "run": d.name, **m, "mean_drop50": m50["mean"],
                         "leader": meta.get("leader"), "leader_after": meta.get("leader_after"),
                         "start_utc": meta.get("start_utc")})
        lats.append(lat)
    sys_lat[sc] = np.concatenate(lats)
write_csv("system_runs.csv", sys_runs)
np.savez_compressed(OUT / "system_latencies.npz", **sys_lat)

sys_sum = {}
for sc in SCEN:
    rs = [r for r in sys_runs if r["scenario"] == sc]
    sys_sum[sc] = {k: ms([r[k] for r in rs]) for k in ("tps", "mean", "p50", "p95", "p99", "mean_drop50")}
    sys_sum[sc]["runs"] = len(rs)
    sys_sum[sc]["sent"] = sum(r["sent"] for r in rs)
    sys_sum[sc]["ok"] = sum(r["ok"] for r in rs)
    sys_sum[sc]["warmup_effect_ms"] = sys_sum[sc]["mean_drop50"][0] - sys_sum[sc]["mean"][0]
summary["system"] = sys_sum

overhead, sys_stats = {}, []
for e, h in PAIRS:
    E, H = sys_sum[e], sys_sum[h]
    overhead[f"{h}_vs_{e}"] = {
        "tps_reduction_pct": (E["tps"][0] - H["tps"][0]) / E["tps"][0] * 100,
        "latency_increase_pct": (H["mean"][0] - E["mean"][0]) / E["mean"][0] * 100,
        "latency_increment_ms": H["mean"][0] - E["mean"][0],
        "p50_increase_pct": (H["p50"][0] - E["p50"][0]) / E["p50"][0] * 100,
        "p95_increase_pct": (H["p95"][0] - E["p95"][0]) / E["p95"][0] * 100,
        "p99_increase_pct": (H["p99"][0] - E["p99"][0]) / E["p99"][0] * 100,
    }
    for metric in ("mean", "p95", "tps"):
        # runs are matched by round (ABBA order), so the paired differences are also reported
        a = [r[metric] for r in sorted((r for r in sys_runs if r["scenario"] == e), key=lambda r: r["run"])]
        b = [r[metric] for r in sorted((r for r in sys_runs if r["scenario"] == h), key=lambda r: r["run"])]
        sys_stats.append({"pair": f"{e}_vs_{h}", "metric": metric, **compare(a, b)})
summary["system_overhead"] = overhead
write_csv("system_stats.csv", sys_stats)

# ---------------------------------------------------------------- resource benchmark
res_runs = []
for sc in SCEN:
    for d in run_dirs("resource", sc, 1):
        meta = kv(d / "run_meta.txt")
        ws, we = num(meta, "workload_start_ms"), num(meta, "workload_end_ms")
        m, _ = tx_metrics(load_tx(d / "invoke_latency.csv"))
        for k in (0, 1):
            f = d / f"resource_peer{k}.csv"
            if not f.exists():
                continue
            r = resource_metrics(f, ws, we)
            if r:
                res_runs.append({"scenario": sc, "run": d.name, "peer": f"peer{k}", **r,
                                 "tps": m["tps"], "lat_mean": m["mean"], "p99": m["p99"], "fail": m["fail"]})
write_csv("resource_runs.csv", res_runs)
res_sum = {}
for sc in SCEN:
    for p in ("peer0", "peer1"):
        rs = [r for r in res_runs if r["scenario"] == sc and r["peer"] == p]
        if rs:
            res_sum[f"{sc}_{p}"] = {k: ms([r[k] for r in rs]) for k in
                                    ("cpu_mean", "cpu_peak", "mem_mean", "rss_mean_mib", "p99", "tps", "temp_max_c", "freq_min_mhz")}
            res_sum[f"{sc}_{p}"]["runs"] = len(rs)
summary["resource"] = res_sum

# ---------------------------------------------------------------- host I/O (system runs: no sampler running)
io_runs = []
for sc in SCEN:
    for d in run_dirs("system", sc, 1):
        meta = kv(d / "run_meta.txt")
        dur = num(meta, "duration_ms") / 1000.0
        sent = num(meta, "sent")
        for k in (0, 1):
            pre, post = kv(d / f"snap_peer{k}_pre.txt"), kv(d / f"snap_peer{k}_post.txt")
            if not pre or not post:
                continue
            rx = num(post, "wlan0_rx") - num(pre, "wlan0_rx")
            tx = num(post, "wlan0_tx") - num(pre, "wlan0_tx")
            wr = (num(post, "mmc_sectors_written") - num(pre, "mmc_sectors_written")) * 512
            blocks = num(post, "ledger_block_processing_time_count") - num(pre, "ledger_block_processing_time_count")
            snap_span = (num(post, "ts") - num(pre, "ts")) / 1000.0
            f = 1000.0 / sent
            io_runs.append({"scenario": sc, "run": d.name, "peer": f"peer{k}",
                            "rx_mib": rx * f / MIB, "tx_mib": tx * f / MIB, "total_mib": (rx + tx) * f / MIB,
                            "kib_s": (rx + tx) / 1024 / snap_span, "disk_write_mib": wr * f / MIB,
                            "rx_bytes_per_tx": rx / sent, "blocks": blocks, "snap_span_s": snap_span, "workload_s": dur})
write_csv("io_runs.csv", io_runs)
io_sum = {}
for sc in SCEN:
    for p in ("peer0", "peer1"):
        rs = [r for r in io_runs if r["scenario"] == sc and r["peer"] == p]
        if rs:
            io_sum[f"{sc}_{p}"] = {k: ms([r[k] for r in rs]) for k in
                                   ("rx_mib", "tx_mib", "total_mib", "kib_s", "disk_write_mib", "rx_bytes_per_tx", "blocks")}
summary["io"] = io_sum
summary["io_growth"] = {}
for e, h in PAIRS:
    for p in ("peer0", "peer1"):
        E, H = io_sum[f"{e}_{p}"], io_sum[f"{h}_{p}"]
        summary["io_growth"][f"{h}_vs_{e}_{p}"] = {
            "total_ratio": H["total_mib"][0] / E["total_mib"][0],
            "rx_growth_bytes_per_tx": H["rx_bytes_per_tx"][0] - E["rx_bytes_per_tx"][0],
            "disk_write_growth_pct": (H["disk_write_mib"][0] / E["disk_write_mib"][0] - 1) * 100,
        }

# ---------------------------------------------------------------- concurrency sweep
sw_runs = []
for sc in SCEN:
    for c in CONCS:
        for d in run_dirs("sweep", sc, c):
            meta = kv(d / "run_meta.txt")
            ws, we = num(meta, "workload_start_ms"), num(meta, "workload_end_ms")
            m, _ = tx_metrics(load_tx(d / "invoke_latency.csv"))
            row = {"scenario": sc, "c": c, "run": d.name, **m}
            for k in (0, 1):
                f = d / f"resource_peer{k}.csv"
                r = resource_metrics(f, ws, we) if f.exists() else None
                row[f"cpu{k}"] = r["cpu_mean"] if r else float("nan")
                row[f"mem{k}"] = r["mem_mean"] if r else float("nan")
            row["rhoT_over_c"] = m["tps"] * m["mean"] / 1000.0 / c
            sw_runs.append(row)
write_csv("sweep_runs.csv", sw_runs)
sw_sum = []
for sc in SCEN:
    for c in CONCS:
        rs = [r for r in sw_runs if r["scenario"] == sc and r["c"] == c]
        row = {"scenario": sc, "c": c, "runs": len(rs), "sent": sum(r["sent"] for r in rs), "ok": sum(r["ok"] for r in rs)}
        for k in ("tps", "mean", "p99", "cpu0", "cpu1", "rhoT_over_c"):
            row[f"{k}_mean"], row[f"{k}_sd"] = ms([r[k] for r in rs])
        row["success_pct"] = row["ok"] / row["sent"] * 100
        sw_sum.append(row)
write_csv("sweep_summary.csv", sw_sum)

gaps = []
for e, h in PAIRS:
    for c in CONCS:
        E = next(r for r in sw_sum if r["scenario"] == e and r["c"] == c)
        H = next(r for r in sw_sum if r["scenario"] == h and r["c"] == c)
        gaps.append({"pair": f"{h}_vs_{e}", "c": c,
                     "tps_penalty_pct": (E["tps_mean"] - H["tps_mean"]) / E["tps_mean"] * 100,
                     "latency_gap_ms": H["mean_mean"] - E["mean_mean"],
                     "p99_hyb": H["p99_mean"], "p99_ecdsa": E["p99_mean"],
                     "cpu0_hyb": H["cpu0_mean"], "cpu0_ecdsa": E["cpu0_mean"]})
write_csv("sweep_gaps.csv", gaps)

laws = []
for sc in SCEN:
    rs = sorted((r for r in sw_sum if r["scenario"] == sc), key=lambda r: r["c"])
    rho = np.array([r["tps_mean"] for r in rs])
    T = np.array([r["mean_mean"] for r in rs])
    lr = stats.linregress(rho, T)
    row = {"scenario": sc, "T0_ms": lr.intercept, "beta_ms_per_tps": lr.slope, "beta_se": lr.stderr, "R2_load": lr.rvalue ** 2}
    for k in (0, 1):
        U = np.array([r[f"cpu{k}_mean"] for r in rs])
        if np.all(np.isfinite(U)):
            lu = stats.linregress(rho, U)
            row[f"U0_peer{k}"] = lu.intercept
            row[f"D_ms_peer{k}"] = lu.slope * 10.0  # (% of a core per TPS) * 10 = ms of CPU per tx
            row[f"D_se_peer{k}"] = lu.stderr * 10.0
            row[f"R2_util_peer{k}"] = lu.rvalue ** 2
            row[f"U_pred_c16_peer{k}"] = lu.intercept + lu.slope * rho[-1]
            row[f"U_meas_c16_peer{k}"] = U[-1]
    laws.append(row)
write_csv("laws.csv", laws)
summary["laws"] = {r["scenario"]: r for r in laws}
summary["sweep_rhoT_over_c_range"] = [float(min(r["rhoT_over_c_mean"] for r in sw_sum)),
                                      float(max(r["rhoT_over_c_mean"] for r in sw_sum))]

# ---------------------------------------------------------------- pprof (peer0, 3 x 60 s per mode)
PPROF_FUNCS = {
    "msp_identity_Verify": r"msp\.\(\*identity\)\.Verify$",
    "tryVerifyHybrid": r"msp\.\(\*identity\)\.tryVerifyHybrid$",
    "VerifyHybridSignature": r"bccsp/signer\.VerifyHybridSignature$",
    "sw_CSP_Verify": r"bccsp/sw\.\(\*CSP\)\.Verify$",
    "ecdsa_Verify": r"^crypto/ecdsa\.Verify$",
    "pq_verify_go": r"bccsp/sw\.verifyPQ$",
    "liboqs_verify_cgo": r"oqs\._Cfunc_OQS_SIG_verify$",
    "liboqs_sign_cgo": r"oqs\._Cfunc_OQS_SIG_sign$",
    "cgocall": r"^runtime\.cgocall$",
    "bft_header_receiver": r"blocksprovider\.\(\*BFTHeaderReceiver\)\.DeliverHeaders$",
    "block_sig_verifier": r"BlockSignatureVerifier\.func\d+$",
    "endorser_process_proposal": r"_Endorser_ProcessProposal_Handler$",
    "gc_bg_mark": r"^runtime\.gcBgMarkWorker$",
    "proto_unmarshal": r"^google\.golang\.org/protobuf/proto\.UnmarshalOptions\.unmarshal$",
}
UNIT = {"ns": 1e-9, "us": 1e-6, "µs": 1e-6, "ms": 1e-3, "s": 1.0, "min": 60.0, "h": 3600.0}


def parse_dur(s):
    m = re.fullmatch(r"([\d.]+)(ns|us|µs|ms|s|min|h)", s)
    return float(m.group(1)) * UNIT[m.group(2)] if m else 0.0


def pprof_top(pb):
    out = subprocess.run(["go", "tool", "pprof", "-top", "-cum", "-nodecount=100000", "-nodefraction=0",
                          "-edgefraction=0", str(pb)], capture_output=True, text=True, check=True).stdout
    total = parse_dur(re.search(r"Total samples = (\S+)", out).group(1))
    cum = {}
    for line in out.splitlines():
        p = line.split()
        if len(p) >= 6 and p[-2].endswith("%") and p[1].endswith("%"):
            cum[" ".join(p[5:])] = parse_dur(p[3])
    return total, cum


pp_rows = []
for sc in ("S1", "S2"):
    d = RES / "pprof" / sc / "run01"
    meta = kv(d / "run_meta.txt")
    txs = load_tx(d / "load_invoke_latency.csv")
    for k in (1, 2, 3):
        total, cum = pprof_top(d / f"profile_{k}.pb")
        pre, post = kv(d / f"snap_w{k}_pre.txt"), kv(d / f"snap_w{k}_post.txt")
        w0, w1 = num(meta, f"window{k}_start_ms"), num(meta, f"window{k}_end_ms")
        row = {"scenario": sc, "window": k, "total_s": total,
               "blocks": num(post, "ledger_block_processing_time_count") - num(pre, "ledger_block_processing_time_count"),
               "proposals": num(post, "endorser_proposals_received") - num(pre, "endorser_proposals_received"),
               "tx_committed_in_window": sum(1 for x in txs if w0 <= x[1] <= w1 and x[3] == 0),
               "cg_cpu_s": (num(post, "cg_cpu_usec") - num(pre, "cg_cpu_usec")) / 1e6}
        for name, pat in PPROF_FUNCS.items():
            row[f"{name}_s"] = sum(v for f, v in cum.items() if re.search(pat, f))
        pp_rows.append(row)
write_csv("pprof_windows.csv", pp_rows)
pp_sum = {}
for sc in ("S1", "S2"):
    rs = [r for r in pp_rows if r["scenario"] == sc]
    tot = sum(r["total_s"] for r in rs)
    blocks = sum(r["blocks"] for r in rs)
    pp_sum[sc] = {"total_s": tot, "blocks": blocks, "cg_cpu_s": sum(r["cg_cpu_s"] for r in rs),
                  "cpu_ms_per_block": tot / blocks * 1000, "cg_cpu_ms_per_block": sum(r["cg_cpu_s"] for r in rs) / blocks * 1000,
                  "share_pct": {n: sum(r[f"{n}_s"] for r in rs) / tot * 100 for n in PPROF_FUNCS},
                  "ms_per_block": {n: sum(r[f"{n}_s"] for r in rs) / blocks * 1000 for n in PPROF_FUNCS},
                  "window_share_identity_verify_pct": [r["msp_identity_Verify_s"] / r["total_s"] * 100 for r in rs]}
summary["pprof"] = pp_sum
summary["pprof_ratio_cpu_per_block"] = pp_sum["S2"]["cpu_ms_per_block"] / pp_sum["S1"]["cpu_ms_per_block"]

# ---------------------------------------------------------------- failures and integrity
fails = []
for phase in ("system", "resource", "sweep"):
    for sc in SCEN:
        for c in (CONCS if phase == "sweep" else [1]):
            for d in run_dirs(phase, sc, c):
                for x in load_tx(d / "invoke_latency.csv"):
                    if x[3] != 0:
                        fails.append({"phase": phase, "scenario": sc, "c": c, "run": d.name, "latency_ms": x[2], "status": x[3]})
write_csv("failures.csv", fails)
summary["failures"] = fails


def jsonable(o):
    if isinstance(o, dict):
        return {k: jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    return o


(OUT / "summary.json").write_text(json.dumps(jsonable(summary), indent=1, ensure_ascii=False))
print(f"wrote {OUT}")
