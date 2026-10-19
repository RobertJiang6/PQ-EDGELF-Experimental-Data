# PQ-EDGELF experimental data

Raw measurements, analysis scripts, and derived results for the paper
*PQ-EDGELF: A Hybrid Post-Quantum Blockchain Edge Framework for the Industrial
Internet of Things* (submitted to the Journal of Systems Architecture).

This repository holds a single dataset: the October 2026 re-measurement on which
every number in the submitted manuscript is based. The hybrid peers run the final
build with strict AND verification and the downgrade check, without diagnostic
code. Data from earlier measurement campaigns has been removed.

## Testbed

- Hyperledger Fabric 3.1.4; SmartBFT ordering service on four x86_64 VMs; orderer1
  leads both networks and was checked before every run.
- Two Raspberry Pi 4B boards (Cortex-A72, 8 GB) as endorsing and committing peers.
- ECDSA network: stock Fabric 3.1.4 peer. Hybrid network: PQ-EDGELF ECDSA+ML-DSA-44
  build (liboqs 0.15.0). Build identifiers are listed in `DESIGN.txt`.

| Scenario | Signatures | Endorsement |
|---|---|---|
| S1 | ECDSA | peer0 |
| S2 | ECDSA + ML-DSA-44 (hybrid) | peer0 |
| S3 | ECDSA | peer0 and peer1 |
| S4 | ECDSA + ML-DSA-44 (hybrid) | peer0 and peer1 |

## Layout and mapping to the paper

| Path | Content | Paper |
|---|---|---|
| `data/results/system/` | 5 runs x 1000 transactions per scenario, closed loop, c = 1; per-transaction latency, run metadata, before/after snapshots of both Pis | Sections 7.3, 7.4; Figs. 4, 5 |
| `data/results/resource/` | 5 further runs per scenario; cgroup CPU of both peer containers every 2 s | Section 7.5 |
| `data/results/sweep/` | c in {1, 2, 4, 8, 16}, 3 runs x 1000 transactions per point | Sections 7.7, 7.10; Fig. 7 |
| `data/results/pprof/` | peer0 Go CPU profiles, three 60-s windows during 900 transactions (S1, S2) | Section 7.6; Fig. 6 |
| `data/results/warmup/` | 20 warm-up transactions before each run (excluded from all statistics) | -- |
| `data/scripts/`, `plan.txt`, `DESIGN.txt` | Orchestration scripts and the counterbalanced run order actually executed | Section 7.1 |
| `analysis/` | `analyze.py` and its outputs (`out/`): run summaries, Mann--Whitney tests, resource, I/O, sweep, operational-law fits, pprof per block, failures | Sections 7.3--7.8, 7.10 |
| `memexp/` | Memory experiment: 3 rounds per scenario (peer restart, 30 s idle, 100 warm-up, 1000 tx at c = 1 and 1000 at c = 16); Go heap and RSS every 2 s; `analyze_mem.py` and `out/` | Section 7.5; Fig. 8(d) |
| `blocks/` | 200 blocks fetched from orderer1 (10 consecutive single-transaction blocks from the middle of each system run); protobuf field-level analysis and block-size model check | Sections 7.9, 7.10; Fig. 8 |
| `primitive_benchmark/` | Falcon-512 vs. ML-DSA-44 key-generation/sign/verify cycle (Raspberry Pi 4B and VM); ML-DSA-44 sign/verify breakdown (C, liboqs, 1000 trials after 50 warm-up); hybrid ASN.1 encode/decode benchmark | Section 5 (primitive selection table); Section 7.10 |
| `tamper/` | All 56 tampering and downgrade cases through the MSP `identity.Verify` entry point, for the final build (`downgrade_cases_strict.csv`) and for the negative control without the downgrade check (`downgrade_cases_baseline.csv`) | Section 6.6; Appendix A |
| `plotting/plot_figs_rerun.py` | Regenerates Figs. 4--8 from this repository | -- |

## Reproducing the results

Python 3 with NumPy, SciPy, and Matplotlib. From the repository root:

```bash
python analysis/analyze.py data analysis/out
python memexp/analyze_mem.py memexp/data memexp/out
python blocks/analyze_blocks.py blocks/raw analysis/out/summary.json blocks/out
python plotting/plot_figs_rerun.py . figures
```

Running the three analysis scripts on the files in this repository reproduces the
committed `out/` files byte for byte.

## Notes

- Latency statistics use successful transactions only. Across the system, resource,
  and sweep experiments three transactions failed, all in S3
  (`analysis/out/failures.csv`); two more failed in the memory experiment, also in S3. Failed transactions are
  reported, not replaced.
- One resource run (S1, run02) was aborted on 2026-10-16 when the second Raspberry Pi
  went offline. It was discarded and repeated; the aborted run is not included.
- The SSH password of the Raspberry Pis has been replaced by the environment variable
  `PI_PASS` in `data/scripts/env.sh` and `memexp/data/scripts/env.sh`. Apart from
  this line, the scripts are the versions that ran; `data/scripts/SHA256SUMS` lists the
  hashes of the as-run files, so only `env.sh` differs.
- The primitive benchmarks do not depend on the Fabric build. The Falcon/ML-DSA cycle
  and the ML-DSA breakdown were measured before the October 2026 re-measurement. The
  ASN.1 benchmark times a Python implementation of the same two-component DER
  layout; its output was not stored in the original run, so it was re-run on the
  same Raspberry Pi (pi1) on 2026-10-19 (`asn1_breakdown_pi1.txt`, 0.009 ms per
  encode + decode).
- Some per-step notes (`blocks/README.md`, `DESIGN.txt` files) are working notes and
  are partly written in Chinese.
