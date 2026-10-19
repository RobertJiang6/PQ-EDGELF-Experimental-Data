"""Figures 4-8 from the 2026-10-16 re-measurement.

Usage: python plot_figs_rerun.py <rerun_dir> <out_dir> [qa_dir]

rerun_dir is 实验补强/rerun_20261016 and must contain
  analysis/out/{summary.json, system_runs.csv, system_latencies.npz, sweep_summary.csv,
                laws.csv, pprof_windows.csv}
  memexp/out/mem_summary.json
  blocks/out/block_summary.json
If qa_dir is given and audit_panel_alignment (nature-figure) is importable, every figure
passes the panel-alignment gate before export and the report is written to qa_dir.
"""
import csv
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.legend_handler import HandlerTuple

try:
    from audit_panel_alignment import require_matplotlib_panel_alignment
except ImportError:
    require_matplotlib_panel_alignment = None

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "mathtext.fontset": "stix",
    "font.size": 9,
    "axes.labelsize": 9,
    "xtick.labelsize": 8.5,
    "ytick.labelsize": 8.5,
    "legend.fontsize": 8,
    "xtick.direction": "in",
    "ytick.direction": "in",
    "xtick.top": True,
    "ytick.right": True,
    "axes.linewidth": 0.8,
    "legend.frameon": True,
    "legend.edgecolor": "0.3",
    "legend.fancybox": False,
    "legend.framealpha": 1.0,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "savefig.dpi": 300,
})

BLUE, ORANGE, RED = "#1f77b4", "#ff7f0e", "#d62728"
LBLUE, LORANGE = "#aec7e8", "#ffbb78"  # light tints for secondary quantities
SCEN = ["S1", "S2", "S3", "S4"]
SUB = {s: rf"$S_{s[1]}$" for s in SCEN}  # subscripted, as in the text and tables
COLOR = {"S1": BLUE, "S2": ORANGE, "S3": BLUE, "S4": ORANGE}
TINT = {"S1": LBLUE, "S2": LORANGE, "S3": LBLUE, "S4": LORANGE}
HATCH = {"S1": "", "S2": "", "S3": "//", "S4": "//"}
LS = {"S1": "-", "S2": "-", "S3": "--", "S4": "--"}
MARK = {"S1": "o", "S2": "s", "S3": "^", "S4": "D"}
LABEL = {"S1": r"$S_1$ (ECDSA, single)", "S2": r"$S_2$ (Hybrid, single)",
         "S3": r"$S_3$ (ECDSA, dual)", "S4": r"$S_4$ (Hybrid, dual)"}
BAR = dict(edgecolor="black", linewidth=0.6)
ERR = dict(ecolor="black", elinewidth=0.7, capsize=2.5)

R = Path(sys.argv[1])
OUT = Path(sys.argv[2])
QA = Path(sys.argv[3]) if len(sys.argv) > 3 else None
A = R / "analysis" / "out"


def rcsv(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def sub(ax, text, y=-0.24):
    ax.text(0.5, y, text, transform=ax.transAxes, ha="center", va="top", fontsize=9.5)


def val(ax, x, y, text, **kw):
    # value label; the white box keeps the dotted grid line from running through the digits
    kw.setdefault("ha", "center")
    kw.setdefault("va", "bottom")
    kw.setdefault("fontsize", 7.5)
    ax.text(x, y, text, bbox=dict(fc="white", ec="none", pad=0.3), **kw)


def ygrid(ax):
    ax.grid(axis="y", linestyle=":", linewidth=0.5, color="0.6")
    ax.set_axisbelow(True)


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    if QA is not None and require_matplotlib_panel_alignment is not None:
        QA.mkdir(parents=True, exist_ok=True)
        require_matplotlib_panel_alignment(fig, json_out=QA / f"{name}.alignment.json",
                                           tolerance_pt=1.5, gutter_tolerance_pt=1.5, strict=True)
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight", pad_inches=0.02)
    fig.savefig(OUT / f"{name}.png", bbox_inches="tight", pad_inches=0.02, dpi=300)
    plt.close(fig)


S = json.load(open(A / "summary.json"))


def fig4():
    sysm = S["system"]
    ov = S["system_overhead"]
    fig, axes = plt.subplots(1, 3, figsize=(7.1, 2.35))
    x = np.arange(4)
    for ax, key, ylab, fmt, top in ((axes[0], "tps", "Throughput (TPS)", "{:.2f}", 3.2),
                                    (axes[1], "mean", "Mean latency (ms)", "{:.0f}", 560)):
        for i, s in enumerate(SCEN):
            m, sd = sysm[s][key]
            ax.bar(i, m, 0.6, yerr=sd, color=COLOR[s], hatch=HATCH[s], error_kw=ERR, **BAR)
            val(ax, i, m + sd + top * 0.015, fmt.format(m))
        ax.set_xticks(x, [SUB[s] for s in SCEN])
        ax.set_ylabel(ylab)
        ax.set_ylim(0, top)
        ygrid(ax)
    sub(axes[0], "(a) Throughput", y=-0.13)
    sub(axes[1], "(b) Mean latency", y=-0.13)

    ax = axes[2]
    # same encoding as (a)/(b): orange = hybrid, hatch = dual endorsement
    pairs = (("S2_vs_S1", "S2", r"$S_2$ vs. $S_1$ (single)"), ("S4_vs_S3", "S4", r"$S_4$ vs. $S_3$ (dual)"))
    w = 0.34
    xp = np.arange(2)
    for k, (p, s, lab) in enumerate(pairs):
        vals = [ov[p]["tps_reduction_pct"], ov[p]["latency_increase_pct"]]
        bars = ax.bar(xp + (k - 0.5) * w, vals, w, color=COLOR[s], hatch=HATCH[s], label=lab, **BAR)
        for b in bars:
            val(ax, b.get_x() + b.get_width() / 2, b.get_height() + 0.2, f"{b.get_height():.2f}")
    ax.set_xticks(xp, ["TPS reduction", "Latency increase"])
    ax.set_ylabel("Hybrid overhead (%)")
    ax.set_ylim(0, 18)
    ax.set_xlim(-0.5, 1.5)
    ax.legend(loc="upper right")
    ygrid(ax)
    sub(ax, "(c) Matched overhead", y=-0.13)
    fig.tight_layout(w_pad=1.6)
    fig.subplots_adjust(bottom=0.14)
    save(fig, "fig4")


def fig5():
    z = np.load(A / "system_latencies.npz")
    runs = rcsv(A / "system_runs.csv")
    fig, axes = plt.subplots(1, 2, figsize=(7.1, 2.6), gridspec_kw={"width_ratios": [1.15, 1]})
    ax = axes[0]
    for s in SCEN:
        v = np.sort(z[s])
        ax.plot(v, np.arange(1, len(v) + 1) / len(v), color=COLOR[s], ls=LS[s], lw=1.2, label=SUB[s])
    # starts below the first tick so that "200" and "0.0" do not meet in the corner
    ax.set_xlim(150, 1400)
    ax.set_xticks(np.arange(200, 1401, 200))
    ax.set_ylim(0, 1.0)
    ax.set_xlabel("End-to-end latency (ms)")
    ax.set_ylabel("CDF")
    ax.grid(linestyle=":", linewidth=0.5, color="0.6")
    ax.legend(loc="lower right")
    sub(ax, "(a) Latency CDF (all successful transactions)", y=-0.27)

    ax = axes[1]
    pct = ["p50", "p95", "p99"]
    w = 0.19
    for j, s in enumerate(SCEN):
        vals = [[float(r[p]) for r in runs if r["scenario"] == s] for p in pct]
        m = [np.mean(v) for v in vals]
        sd = [np.std(v, ddof=1) for v in vals]
        ax.bar(np.arange(3) + (j - 1.5) * w, m, w, yerr=sd, color=COLOR[s], hatch=HATCH[s],
               label=SUB[s], error_kw=dict(ERR, capsize=1.8), **BAR)
    ax.set_xticks(np.arange(3), ["P50", "P95", "P99"])
    ax.set_ylabel("Latency (ms)")
    ax.set_ylim(0, 1500)
    ax.legend(loc="upper left", ncol=2)
    ygrid(ax)
    sub(ax, "(b) Per-run percentiles (mean of 5 runs)", y=-0.27)
    fig.tight_layout(w_pad=2.0)
    fig.subplots_adjust(bottom=0.24)
    save(fig, "fig5")


def fig6():
    rows = rcsv(A / "pprof_windows.csv")

    def per_block(sc, key):
        v = [float(r[key]) * 1000 / float(r["blocks"]) for r in rows if r["scenario"] == sc]
        return np.mean(v), np.std(v, ddof=1)

    common = [("total_s", "Whole profile"),
              ("msp_identity_Verify_s", "identity.Verify"),
              ("sw_CSP_Verify_s", "CSP.Verify"),
              ("ecdsa_Verify_s", "ecdsa.Verify"),
              ("block_sig_verifier_s", "BlockSignatureVerifier"),
              ("bft_header_receiver_s", "BFTHeaderReceiver"),
              ("endorser_process_proposal_s", "ProcessProposal")]
    hyb = [("tryVerifyHybrid_s", "tryVerifyHybrid"),
           ("VerifyHybridSignature_s", "VerifyHybridSignature"),
           ("pq_verify_go_s", "sw.verifyPQ"),
           ("liboqs_verify_cgo_s", "OQS_SIG_verify (cgo)"),
           ("liboqs_sign_cgo_s", "OQS_SIG_sign (cgo)")]
    fig, axes = plt.subplots(1, 2, figsize=(7.1, 2.75), gridspec_kw={"width_ratios": [1.25, 1]})
    ax = axes[0]
    y = np.arange(len(common))[::-1]
    h = 0.36
    for k, (sc, name, col) in enumerate((("S1", r"ECDSA ($S_1$)", BLUE), ("S2", r"Hybrid ($S_2$)", ORANGE))):
        st = [per_block(sc, key) for key, _ in common]
        ax.barh(y + (0.5 - k) * h, [m for m, _ in st], h, xerr=[s for _, s in st], color=col,
                label=name, error_kw=dict(ERR, capsize=1.8), **BAR)
    ax.set_yticks(y, [n for _, n in common])
    ax.set_xlabel("CPU time per committed block (ms)")
    ax.set_xlim(0, 100)
    ax.legend(loc="lower right")
    ax.grid(axis="x", linestyle=":", linewidth=0.5, color="0.6")
    ax.set_axisbelow(True)
    sub(ax, "(a) Functions present in both modes", y=-0.2)

    ax = axes[1]
    y = np.arange(len(hyb))[::-1]
    st = [per_block("S2", key) for key, _ in hyb]
    bars = ax.barh(y, [m for m, _ in st], 0.55, xerr=[s for _, s in st], color=ORANGE,
                   error_kw=dict(ERR, capsize=1.8), **BAR)
    for b, (m, sd) in zip(bars, st):
        # measured from the end of the error bar, so the cap is not read as a "+" sign
        val(ax, m + sd + 1.5, b.get_y() + b.get_height() / 2, f"{m:.1f}", ha="left", va="center")
    ax.set_yticks(y, [n for _, n in hyb])
    ax.set_xlabel("CPU time per committed block (ms)")
    ax.set_xlim(0, 50)
    ax.grid(axis="x", linestyle=":", linewidth=0.5, color="0.6")
    ax.set_axisbelow(True)
    sub(ax, r"(b) Hybrid-only functions ($S_2$)", y=-0.2)
    fig.tight_layout(w_pad=1.5)
    fig.subplots_adjust(bottom=0.22)
    save(fig, "fig6")


def fig7():
    sw = rcsv(A / "sweep_summary.csv")
    laws = {r["scenario"]: r for r in rcsv(A / "laws.csv")}
    fig, axes = plt.subplots(1, 3, figsize=(7.1, 2.45))
    for s in SCEN:
        rs = sorted((r for r in sw if r["scenario"] == s), key=lambda r: int(r["c"]))
        c = [int(r["c"]) for r in rs]
        kw = dict(color=COLOR[s], ls=LS[s], marker=MARK[s], ms=4, lw=1.1, mfc="white", mew=1.0,
                  capsize=2, elinewidth=0.7)
        axes[0].errorbar(c, [float(r["tps_mean"]) for r in rs], yerr=[float(r["tps_sd"]) for r in rs],
                         label=LABEL[s], **kw)
        axes[1].errorbar(c, [float(r["mean_mean"]) for r in rs], yerr=[float(r["mean_sd"]) for r in rs], **kw)
        rho = np.array([float(r["tps_mean"]) for r in rs])
        # points on top, thin fit lines underneath and only over the measured range
        axes[2].errorbar(rho, [float(r["cpu0_mean"]) for r in rs], yerr=[float(r["cpu0_sd"]) for r in rs],
                         xerr=[float(r["tps_sd"]) for r in rs], color=COLOR[s], ls="none", marker=MARK[s],
                         ms=4, mfc="white", mew=1.0, capsize=1.2, elinewidth=0.5, zorder=3)
        L = laws[s]
        xx = np.linspace(rho.min() - 0.8, rho.max() + 0.8, 50)
        axes[2].plot(xx, float(L["U0_peer0"]) + float(L["D_ms_peer0"]) / 10 * xx, color=COLOR[s], ls=LS[s],
                     lw=0.8, alpha=0.8, zorder=1)
    for ax in axes[:2]:
        ax.set_xscale("log", base=2)
        ax.set_xticks([1, 2, 4, 8, 16], ["1", "2", "4", "8", "16"])
        ax.minorticks_off()
        ax.set_xlabel("Concurrent client sessions")
        ax.grid(linestyle=":", linewidth=0.5, color="0.6")
    axes[0].set_ylabel("Throughput (TPS)")
    axes[0].set_ylim(0, 20)
    axes[0].legend(loc="upper left", fontsize=7.5)
    axes[1].set_ylabel("Mean latency (ms)")
    axes[1].set_ylim(300, 1200)
    ax = axes[2]
    ax.set_xlabel("Throughput (TPS)")
    ax.set_ylabel("peer0 CPU (% of one core)")
    ax.set_xlim(0, 20)
    ax.set_ylim(10, 55)
    ax.grid(linestyle=":", linewidth=0.5, color="0.6")
    ax.set_axisbelow(True)
    sub(axes[0], "(a) Throughput")
    sub(axes[1], "(b) Mean latency")
    sub(ax, "(c) peer0 CPU and utilization-law fit")
    fig.tight_layout(w_pad=1.3)
    fig.subplots_adjust(bottom=0.22)
    save(fig, "fig7")


MLDSA44_SIG = 2420  # FIPS 204 ML-DSA-44 signature length


def fig8():
    B = json.load(open(R / "blocks" / "out" / "block_summary.json"))
    M = json.load(open(R / "memexp" / "out" / "mem_summary.json"))["summary"]
    blk = B["blocks"]
    obj = B["objects"]
    mdl = B["model"]
    d_sig, d_cert, q = mdl["delta_sigma"], mdl["delta_c"], mdl["q_hybrid"]
    fig, axes = plt.subplots(2, 2, figsize=(7.1, 5.0))

    ax = axes[0, 0]
    # certificates carried in transactions (creator and endorsers), as found in the inspected blocks
    vals = [obj["clean"]["cert"][0], obj["hybrid"]["cert"][0]]
    bars = ax.bar(["ECDSA", "Hybrid"], vals, 0.45, color=[BLUE, ORANGE], **BAR)
    for b, v in zip(bars, vals):
        val(ax, b.get_x() + b.get_width() / 2, v + 60, f"{v:.0f}", fontsize=8)
    ax.set_ylabel("Certificate size (bytes)")
    ax.set_ylim(0, 4000)
    ygrid(ax)
    sub(ax, "(a) Signing certificate in transactions", y=-0.17)

    ax = axes[0, 1]
    vals = [obj["clean"]["sig"][0], MLDSA44_SIG, obj["hybrid"]["sig"][0]]
    bars = ax.bar(["ECDSA (DER)", "ML-DSA-44", "Hybrid (ASN.1)"], vals, 0.45,
                  color=[BLUE, LORANGE, ORANGE], **BAR)
    for b, v in zip(bars, vals):
        val(ax, b.get_x() + b.get_width() / 2, v + 50, f"{v:.1f}" if v < 100 or v % 1 else f"{v:.0f}",
            fontsize=8)
    ax.set_ylabel("Signature size (bytes)")
    ax.set_ylim(0, 3000)
    ygrid(ax)
    sub(ax, "(b) Signature object", y=-0.17)

    ax = axes[1, 0]
    base_of = {"S2": "S1", "S4": "S3"}
    ne = {"S2": 1, "S4": 2}
    for i, s in enumerate(SCEN):
        if s in ("S1", "S3"):
            ax.bar(i, blk[s]["block"][0], 0.55, color=BLUE, hatch=HATCH[s], **BAR)
            val(ax, i, blk[s]["block"][0] + 500, f"{blk[s]['block'][0]:.0f}", fontsize=8)
            continue
        bottom = blk[base_of[s]]["block"][0]
        ax.bar(i, bottom, 0.55, color=BLUE, hatch=HATCH[s], **BAR)
        for h, fc in (((2 + ne[s]) * d_cert, LORANGE), ((1 + ne[s]) * d_sig, ORANGE)):
            ax.bar(i, h, 0.55, bottom=bottom, color=fc, **BAR)
            bottom += h
        # q*Δσ: grey dots (matplotlib 3.10 has no separate hatch colour), black outline drawn on top
        ax.bar(i, q * d_sig, 0.55, bottom=bottom, color="white", edgecolor="0.6", hatch="...", linewidth=0)
        ax.bar(i, q * d_sig, 0.55, bottom=bottom, fill=False, **BAR)
        bottom += q * d_sig
        meas = blk[s]["block"][0]
        ax.plot(i, meas, marker="*", ms=9, mfc=RED, mec="black", mew=0.5, ls="none", zorder=5)
        val(ax, i, bottom + 1800, f"meas. {meas:.0f}\nmodel {bottom:.0f}", linespacing=1.1)
    ax.set_xticks(range(4), [SUB[s] for s in SCEN])
    ax.set_ylabel("Block size (bytes)")
    ax.set_ylim(0, 50000)
    rect = lambda **kw: plt.Rectangle((0, 0), 1, 1, **kw)
    dots = (rect(fc="white", ec="0.6", lw=0, hatch="..."), rect(fill=False, ec="black", lw=0.6))
    handles = [rect(fc=BLUE, ec="black", lw=0.6), rect(fc=LORANGE, ec="black", lw=0.6),
               rect(fc=ORANGE, ec="black", lw=0.6), dots,
               plt.Line2D([], [], marker="*", ms=9, mfc=RED, mec="black", mew=0.5, ls="none")]
    # "50 blocks" is in the caption; a short entry keeps the legend clear of the S4 label
    ax.legend(handles, ["ECDSA block", r"$(2+n_e)\Delta c$", r"$(1+n_e)\Delta\sigma$", r"$q\Delta\sigma$",
                        "Measured"], loc="upper left", ncol=2, fontsize=7.5,
              handler_map={tuple: HandlerTuple(ndivide=1, pad=0)})
    ygrid(ax)
    sub(ax, "(c) Single-transaction block", y=-0.17)

    ax = axes[1, 1]
    peers = {"S1": ["peer0"], "S2": ["peer0"], "S3": ["peer0", "peer1"], "S4": ["peer0", "peer1"]}
    cpu = [np.mean([S["resource"][f"{s}_{p}"]["cpu_mean"][0] for p in peers[s]]) for s in SCEN]
    cpu_sd = [np.mean([S["resource"][f"{s}_{p}"]["cpu_mean"][1] for p in peers[s]]) for s in SCEN]
    rss = [np.mean([M[f"{s}_{p}"]["c1_rss_med"][0] for p in peers[s]]) for s in SCEN]
    rss_sd = [np.mean([M[f"{s}_{p}"]["c1_rss_med"][1] for p in peers[s]]) for s in SCEN]
    x = np.arange(4)
    w = 0.36
    ax2 = ax.twinx()
    ax2.tick_params(direction="in")
    # scenario colours as in Fig. 4; full colour = CPU (left axis), light tint = RSS (right axis)
    for i, s in enumerate(SCEN):
        ax.bar(i - w / 2, cpu[i], w, yerr=cpu_sd[i], color=COLOR[s], hatch=HATCH[s], error_kw=ERR, **BAR)
        ax2.bar(i + w / 2, rss[i], w, yerr=rss_sd[i], color=TINT[s], hatch=HATCH[s], error_kw=ERR, **BAR)
    ax.set_xticks(x, [SUB[s] for s in SCEN])
    ax.set_ylabel("Peer CPU (% of one core)")
    ax2.set_ylabel("Peer RSS (MiB)")
    ax.set_ylim(0, 30)
    ax2.set_ylim(0, 300)
    ax.tick_params(right=False)
    patch = lambda fc: plt.Rectangle((0, 0), 1, 1, fc=fc, ec="black", lw=0.6)
    ax.legend([(patch(BLUE), patch(ORANGE)), (patch(LBLUE), patch(LORANGE))],
              ["CPU (resource benchmark)", "RSS (memory experiment, $c$=1)"], loc="upper left",
              fontsize=7.5, handlelength=2.6, handler_map={tuple: HandlerTuple(ndivide=None, pad=0)})
    ygrid(ax)
    sub(ax, "(d) Endorsing-peer resources", y=-0.17)
    fig.tight_layout(h_pad=2.6, w_pad=2.2)
    save(fig, "fig8")
    print("fig8 cpu", np.round(cpu, 2), "rss", np.round(rss, 1))


if __name__ == "__main__":
    fig4(); fig5(); fig6(); fig7(); fig8()
