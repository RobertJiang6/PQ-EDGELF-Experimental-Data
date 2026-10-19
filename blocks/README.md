# 第②步：区块结构与字节模型复核（2026-10-17）

## 做法
- `fetch_blocks.sh`（VM1 `scripts/`）：对 20 组 c=1 system run，取区块号 `height_p0_pre+500 … +509`（每轮中段 10 个连续区块），
  从该网络的 orderer1 `peer channel fetch`。共 4 场景 × 5 轮 × 10 = 200 个区块，全部成功。VM1 副本：`/home/sspu/pqedgelf-rerun-20261016/blocks/`，本地：`raw/`。
- `analyze_blocks.py`：自写 protobuf 线格式解析（不依赖 protobuf 库），逐字段统计长度；每个区块都校验了"恰好 1 笔交易"和区块号。
  `python -I analyze_blocks.py raw ../analysis/out/summary.json out` → `out/block_rows.csv`、`out/block_summary.json`。
- Δσ、Δc 直接取自这些区块里的对象：每个网络 550 个签名（信封、背书、共识者）、250 个证书（creator + 背书者）。

## 区块结构（字节，50 个区块的均值 ± 标准差）
| 场景 | Block | Env. sig | Payload | Data | Metadata |
|---|---|---|---|---|---|
| S1 | 3716.1 ± 1.4 | 70.5 | 3218.1 | 3296.6 | 339.5 |
| S2 | 23261.2 ± 1.3 | 2500.6 | 13037.1 | 15546.7 | 7634.5 |
| S3 | 4616.3 ± 1.5 | 70.4 | 4118.5 | 4196.9 | 339.4 |
| S4 | 29061.7 ± 1.5 | 2500.5 | 18834.6 | 21346.2 | 7634.5 |

比旧表大约 56 B，原因是新脚本的交易 key 更长（`<tag>_cNN_tNNNN_<ns>`），两套网络一样，Δ 不受影响。
q = 3（两套网络每个区块都正好 3 个共识者签名，签名里只有 identifier header，不带证书）。

对象：ECDSA 签名 70.47 B（low-S，69–71），混合签名 2500.50 B（2499–2501），Δσ = 2430.03 B；
证书 ECDSA 均值 810 B（User1 814、peer0 806、peer1 810），混合 3276 B，Δc = 2466 B。

## 区块模型（式 block-model，无拟合参数）
| | 模型 | 实测 | 误差 |
|---|---|---|---|
| S2 区块 | 23 264 | 23 261 | +3 B |
| S4 区块 | 29 061 | 29 062 | −1 B |

分项（实测增长）：metadata +7295 ≈ 3Δσ；payload header +2462 = creator 证书；payload data +7357（S2）/ +12 254（S4）
= 第二份 creator 证书 + 每个背书的 Δσ+Δc。占比：证书 38% / 40%，共识者签名 37% / 30%，交易自身签名 25% / 30%（和旧稿一样）。

## 接收字节模型（式 rx-model）
| 对象 | 实测增长 B/tx | 论文原式 | 比值 | 加 deliver 请求项 | 比值 |
|---|---|---|---|---|---|
| S2 vs S1, peer0（背书） | 56 496 | 46 315 | 0.82 | 51 211 | **0.91** |
| S2 vs S1, peer1（不背书） | 46 144 | 41 418 | 0.90 | 41 418 | **0.90** |
| S4 vs S3, peer0 | 61 933 | 51 211 | 0.83 | 56 107 | **0.91** |
| S4 vs S3, peer1 | 61 841 | 51 211 | 0.83 | 56 107 | **0.91** |

- 漏掉的一项：`peer chaincode invoke --waitForEvent` 会对每个 `--peerAddresses` 开一个 DeliverFiltered 流，并发送一个签名的
  DELIVER_SEEK_INFO 信封（带 creator 证书和签名），见 `fabric/internal/peer/chaincode/common.go` 376–395、565–569、691–702、789–828（本地源码 a2abded，与部署版一致）。
  所以客户端连接的 peer 每笔交易收到 **两条** 签名消息（提案 + deliver 请求），不是一条。
- 独立验证：单背书时 peer0 − peer1 的接收差值从 S1 的 8 120 B 涨到 S2 的 18 472 B，增长 10 353 B；两条签名消息的预测是 2(Δσ+Δc) = 9 792 B（只算一条是 4 896 B）。
- BFT 头部副本也核对过源码：`common/deliver/deliver.go:338` 对 HEADER_WITH_SIG 只发 Header + Metadata，所以每份副本增加 qΔσ。
- 剩下约 9–10%（4.7–5.8 kB/tx），估算可以由两部分解释：(i) 链路帧开销 ≈ 4.6%（每 1448 B 段 66 B 的 Ethernet/IP/TCP 头）+ TLS/HTTP2 帧，
  约 2.5–2.7 kB；(ii) gossip：每笔交易约 0.85–0.95 条（约 2.2 条/s，两套网络相同，按时间驱动），如果每条都带混合签名，约 2.3 kB。
  这是量级估算，没有逐包测量。
- 只看信封签名字段 Δσ：3.9–5.3%。
