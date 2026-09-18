# PQ-EDGELF experimental CSV data

This folder collects the CSV files 
The files are  from the existing experiment records; the original files
were not changed or deleted.

## Folder map

- `01_system_benchmark/`: the four formal scenarios, five runs per scenario,
  including the 20 per-transaction latency CSVs and the final summary and
  overhead tables. These support the end-to-end benchmark, latency distribution,
  and Figures 4--5.
- `02_resource_benchmark/`: the final five-run Raspberry Pi resource summary
  used by the resource table and Figure 8(d).
- `03_primitive_benchmark/`: ML-DSA/Falcon primitive summaries, per-run
  primitive measurements, and the Raspberry Pi signing/verification breakdown.
- `04_statistical_tests/`: Wilcoxon, permutation-test, bootstrap-CI, and
  rank-biserial results used in the system-benchmark statistics section.
- `05_concurrency/`: the 1/2/4/8/16-client concurrency scan across S1--S4,
  three runs per point.
- `06_io/`: the network and disk I/O summary plus the four workload-window CSVs
  used to define the I/O measurement windows.
- `07_size_and_block_overhead/`: certificate, signature-object, block-size,
  block-inspection, and 40-block T7 breakdown data.
- `08_tamper/`: the organized 50-case tampering records and the original
  formal-batch result table.

## Scenario labels

- `S1`: ECDSA, single endorsement (`peer0_only`)
- `S2`: Hybrid ECDSA + ML-DSA-44, single endorsement (`peer0_only`)
- `S3`: ECDSA, dual endorsement (`peer0_peer1`)
- `S4`: Hybrid ECDSA + ML-DSA-44, dual endorsement (`peer0_peer1`)

