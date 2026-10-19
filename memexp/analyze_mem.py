"""Analysis of the PQ-EDGELF memory experiment (2026-10-17).

Usage: python analyze_mem.py <exp_dir> <out_dir>
  exp_dir: local copy of VM1 pqedgelf-mem-20261017 (contains results/<S>/<runNN>/)

Per run and peer, phases are taken from run_meta.txt:
  idle  = [idle_start_ms, idle_end_ms]       (after restart, before any transaction)
  c1    = second half of [c1_start_ms, c1_end_ms]   (steady state under one client)
  c16   = [c16_start_ms, c16_end_ms]         (16 clients)
Reported: median and maximum of Go heap in use, process RSS, and (pi1 only) cgroup memory
without inactive file pages. Units: MiB.
"""
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np

EXP, OUT = Path(sys.argv[1]), Path(sys.argv[2])
RUN_PAT = sys.argv[3] if len(sys.argv) > 3 else r"run\d\d"  # e.g. "smoke\d\d" for the smoke test
OUT.mkdir(parents=True, exist_ok=True)
SCEN = ["S1", "S2", "S3", "S4"]
PAIRS = [("S1", "S2"), ("S3", "S4")]
MIB = 1024 * 1024
FIELDS = {"heap_inuse": "heap_inuse", "heap_alloc": "heap_alloc", "rss": "process_rss", "go_sys": "go_sys"}


def kv(p):
    return {k: v.strip('"') for k, v in (l.split("=", 1) for l in p.read_text().splitlines() if "=" in l)}


def samples(p):
    with open(p, newline="") as f:
        return [{k: (float(v) if v not in ("", None) else np.nan) for k, v in r.items()} for r in csv.DictReader(f)]


def window(s, a, b):
    return [x for x in s if a <= x["ts_ms"] <= b]


def tx_stats(p):
    with open(p, newline="") as f:
        rows = list(csv.DictReader(f))
    ok = [r for r in rows if r["status"] == "0"]
    lat = np.array([float(r["latency_ms"]) for r in ok])
    span = (max(int(r["end_ms"]) for r in ok) - min(int(r["start_ms"]) for r in ok)) / 1000
    return {"sent": len(rows), "ok": len(ok), "tps": len(ok) / span, "lat_mean": float(lat.mean())}


rows = []
for sc in SCEN:
    base = EXP / "results" / sc
    for d in sorted(base.iterdir()) if base.exists() else []:
        if not re.fullmatch(RUN_PAT, d.name) or not (d / "DONE").exists():
            continue
        m = {k: float(v) for k, v in kv(d / "run_meta.txt").items() if re.fullmatch(r"[\d.]+", v)}
        c1a, c1b = m["c1_start_ms"], m["c1_end_ms"]
        phases = {"idle": (m["idle_start_ms"], m["idle_end_ms"]), "c1": ((c1a + c1b) / 2, c1b),
                  "c16": (m["c16_start_ms"], m["c16_end_ms"])}
        tx = {ph: tx_stats(d / f"{ph}_latency.csv") for ph in ("c1", "c16")}
        for k in (0, 1):
            s = samples(d / f"mem_peer{k}.csv")
            row = {"scenario": sc, "run": d.name, "peer": f"peer{k}",
                   "c1_ok": tx["c1"]["ok"], "c16_ok": tx["c16"]["ok"],
                   "c1_tps": tx["c1"]["tps"], "c16_tps": tx["c16"]["tps"]}
            for ph, (a, b) in phases.items():
                w = window(s, a, b)
                row[f"{ph}_n"] = len(w)
                for name, col in FIELDS.items():
                    v = np.array([x[col] for x in w]) / MIB
                    row[f"{ph}_{name}_med"] = float(np.nanmedian(v)) if len(v) else np.nan
                    row[f"{ph}_{name}_max"] = float(np.nanmax(v)) if len(v) else np.nan
                cg = np.array([x["cg_mem_current"] - x["cg_inactive_file"] for x in w]) / MIB
                row[f"{ph}_cgmem_med"] = float(np.nanmedian(cg)) if np.isfinite(cg).any() else np.nan
                row[f"{ph}_cgmem_max"] = float(np.nanmax(cg)) if np.isfinite(cg).any() else np.nan
                row[f"{ph}_goroutines_med"] = float(np.nanmedian([x["goroutines"] for x in w])) if w else np.nan
            rows.append(row)

with open(OUT / "mem_runs.csv", "w", newline="") as f:
    w = csv.DictWriter(f, list(rows[0].keys()))
    w.writeheader()
    for r in rows:
        w.writerow({k: (f"{v:.6g}" if isinstance(v, float) else v) for k, v in r.items()})

METRICS = [k for k in rows[0] if re.match(r"(idle|c1|c16)_(heap|rss|go_sys|cgmem|goroutines)", k)]
summ = {}
for sc in SCEN:
    for p in ("peer0", "peer1"):
        rs = [r for r in rows if r["scenario"] == sc and r["peer"] == p]
        if not rs:
            continue
        summ[f"{sc}_{p}"] = {"runs": len(rs)}
        for k in METRICS:
            v = np.array([r[k] for r in rs], float)
            summ[f"{sc}_{p}"][k] = [float(np.nanmean(v)), float(np.nanstd(v, ddof=1)) if np.isfinite(v).sum() > 1 else 0.0]
diff = {}
for e, h in PAIRS:
    for p in ("peer0", "peer1"):
        E, H = summ.get(f"{e}_{p}"), summ.get(f"{h}_{p}")
        if E and H:
            diff[f"{h}_vs_{e}_{p}"] = {k: H[k][0] - E[k][0] for k in METRICS}
(OUT / "mem_summary.json").write_text(json.dumps({"summary": summ, "hybrid_minus_ecdsa": diff}, indent=1))
print(f"{len(rows)} peer-runs -> {OUT}")
