#!/usr/bin/env python3
"""Block-structure statistics and byte-model checks for the 2026-10-16 re-measurement.

Usage: python -I analyze_blocks.py <raw_dir> <summary.json> <out_dir>

  raw_dir      blocks fetched by fetch_blocks.sh: <S>/<run>/<num>.block (orderer1 copies)
  summary.json analysis/out/summary.json (host I/O per transaction from the system runs)

No protobuf library is used: a minimal wire-format reader walks the Fabric messages
  Block{header=1, data=2, metadata=3}           BlockData{data=1*}   BlockMetadata{metadata=1*}
  Envelope{payload=1, signature=2}              Payload{header=1, data=2}
  Header{channel_header=1, signature_header=2}  SignatureHeader{creator=1, nonce=2}
  SerializedIdentity{mspid=1, id_bytes=2}       Transaction{actions=1*}
  TransactionAction{header=1, payload=2}        ChaincodeActionPayload{proposal_payload=1, action=2}
  ChaincodeEndorsedAction{prp=1, endorsements=2*}  Endorsement{endorser=1, signature=2}
  Metadata{value=1, signatures=2*}              MetadataSignature{sig_header=1, signature=2, identifier_header=3}
Sizes are serialized field lengths in bytes; "framing" is what a field adds beyond its children.
"""
import csv, json, os, statistics as st, sys

SCEN = {"S1": ("clean", 1), "S2": ("hybrid", 1), "S3": ("clean", 2), "S4": ("hybrid", 2)}
N_ORDERERS = 4


def varint(b, i):
    v = s = 0
    while True:
        c = b[i]; i += 1
        v |= (c & 0x7F) << s; s += 7
        if c < 0x80:
            return v, i


def fields(b):
    """Yield (field_no, wire_type, value) of one message; value is bytes for length-delimited."""
    i = 0
    while i < len(b):
        key, i = varint(b, i)
        fn, wt = key >> 3, key & 7
        if wt == 0:
            v, i = varint(b, i)
        elif wt == 2:
            n, i = varint(b, i); v = b[i:i + n]; i += n
        elif wt == 1:
            v = b[i:i + 8]; i += 8
        elif wt == 5:
            v = b[i:i + 4]; i += 4
        else:
            raise ValueError(f"wire type {wt}")
        yield fn, wt, v


def get(b, fn):
    return [v for f, _, v in fields(b) if f == fn]


def one(b, fn, default=b""):
    r = get(b, fn)
    return r[0] if r else default


def ident(ser):
    """SerializedIdentity -> (mspid, cert bytes)."""
    return one(ser, 1).decode(), one(ser, 2)


def parse_block(raw):
    hdr, data, meta = one(raw, 1), one(raw, 2), one(raw, 3)
    envs = get(data, 1)
    metas = get(meta, 1)
    if len(envs) != 1:
        raise ValueError(f"expected 1 tx, got {len(envs)}")
    env = envs[0]
    payload, env_sig = one(env, 1), one(env, 2)
    p_hdr, p_data = one(payload, 1), one(payload, 2)
    sig_hdr = one(p_hdr, 2)
    _, creator_cert = ident(one(sig_hdr, 1))
    acts = get(p_data, 1)
    if len(acts) != 1:
        raise ValueError("expected 1 action")
    act_hdr, act_pl = one(acts[0], 1), one(acts[0], 2)
    _, act_creator = ident(one(act_hdr, 1))
    cea = one(act_pl, 2)
    prp = one(cea, 1)
    endos = get(cea, 2)
    endo_sig = [len(one(e, 2)) for e in endos]
    endo_cert = [len(ident(one(e, 1))[1]) for e in endos]
    sigmeta = metas[0] if metas else b""
    msigs = get(sigmeta, 2)
    cons_sig = [len(one(m, 2)) for m in msigs]
    cons_has_cert = any(len(one(m, 1)) > 0 for m in msigs)
    num = one(hdr, 1, 0)
    return {
        "number": num, "block": len(raw), "header": len(hdr), "data": len(data), "metadata": len(meta),
        "envelope": len(env), "env_sig": len(env_sig), "payload": len(payload),
        "payload_header": len(p_hdr), "payload_data": len(p_data),
        "creator_cert": len(creator_cert), "action_creator_cert": len(act_creator),
        "prp": len(prp), "n_endorse": len(endos),
        "endo_sig_sum": sum(endo_sig), "endo_cert_sum": sum(endo_cert),
        "endo_sigs": ";".join(map(str, endo_sig)), "endo_certs": ";".join(map(str, endo_cert)),
        "n_consenter_sig": len(cons_sig), "cons_sig_sum": sum(cons_sig),
        "cons_sigs": ";".join(map(str, cons_sig)), "cons_sig_has_cert": int(cons_has_cert),
        "meta_signatures": len(sigmeta), "meta_entries": len(metas),
    }


def ms(xs):
    xs = list(xs)
    return [st.mean(xs), st.stdev(xs) if len(xs) > 1 else 0.0, min(xs), max(xs)]


def main(raw_dir, summary_path, out):
    os.makedirs(out, exist_ok=True)
    rows = []
    for s in sorted(SCEN):
        for run in sorted(os.listdir(os.path.join(raw_dir, s))):
            d = os.path.join(raw_dir, s, run)
            for f in sorted(os.listdir(d)):
                if f.endswith(".block"):
                    with open(os.path.join(d, f), "rb") as fh:
                        r = parse_block(fh.read())
                    if r["number"] != int(f[:-6]):
                        raise ValueError(f"{s}/{run}/{f}: header number {r['number']}")
                    rows.append({"scenario": s, "run": run, **r})
    keys = list(rows[0])
    with open(os.path.join(out, "block_rows.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, keys); w.writeheader(); w.writerows(rows)

    num_cols = [k for k in keys if k not in ("scenario", "run", "number", "endo_sigs", "endo_certs", "cons_sigs")]
    summ = {}
    for s in SCEN:
        R = [r for r in rows if r["scenario"] == s]
        summ[s] = {"blocks": len(R), "runs": len(set(r["run"] for r in R)),
                   **{k: ms(r[k] for r in R) for k in num_cols}}

    # Object sizes measured in the blocks themselves (all signatures / certificates of each network).
    def pool(net, what):
        v = []
        for r in rows:
            if SCEN[r["scenario"]][0] != net:
                continue
            if what == "sig":
                v += [r["env_sig"]] + [int(x) for x in r["endo_sigs"].split(";")] + [int(x) for x in r["cons_sigs"].split(";")]
            elif what == "tx_sig":
                v += [r["env_sig"]] + [int(x) for x in r["endo_sigs"].split(";")]
            elif what == "cons_sig":
                v += [int(x) for x in r["cons_sigs"].split(";")]
            elif what == "cert":
                v += [r["creator_cert"]] + [int(x) for x in r["endo_certs"].split(";")]
        return v

    obj = {net: {w: ms(pool(net, w)) + [len(pool(net, w))] for w in ("sig", "tx_sig", "cons_sig", "cert")}
           for net in ("clean", "hybrid")}
    d_sig = obj["hybrid"]["sig"][0] - obj["clean"]["sig"][0]
    d_cert = obj["hybrid"]["cert"][0] - obj["clean"]["cert"][0]
    q = round(summ["S2"]["n_consenter_sig"][0])
    q_e = round(summ["S1"]["n_consenter_sig"][0])

    model = {"delta_sigma": d_sig, "delta_c": d_cert, "q_hybrid": q, "q_clean": q_e, "N_o": N_ORDERERS, "pairs": {}}
    io = json.load(open(summary_path))["io"]
    for hyb, base in (("S2", "S1"), ("S4", "S3")):
        ne = SCEN[hyb][1]
        d_blk = (1 + ne + q) * d_sig + (2 + ne) * d_cert
        pred = summ[base]["block"][0] + d_blk
        meas = summ[hyb]["block"][0]
        hdr_copies = (N_ORDERERS - 1) * q * d_sig
        signed_req = d_sig + d_cert            # one signed message carrying creator cert + signature
        p = {"n_e": ne, "delta_block_model": d_blk, "delta_block_measured": meas - summ[base]["block"][0],
             "block_pred": pred, "block_meas": meas, "block_err": pred - meas,
             "terms": {"tx_signatures": (1 + ne) * d_sig, "consenter_signatures": q * d_sig,
                       "certificates": (2 + ne) * d_cert},
             "decomp_measured": {
                 "metadata": summ[hyb]["metadata"][0] - summ[base]["metadata"][0],
                 "payload_header": summ[hyb]["payload_header"][0] - summ[base]["payload_header"][0],
                 "payload_data": summ[hyb]["payload_data"][0] - summ[base]["payload_data"][0],
                 "env_sig": summ[hyb]["env_sig"][0] - summ[base]["env_sig"][0]},
             "rx": {}}
        for peer in ("peer0", "peer1"):
            endorser = peer == "peer0" or ne == 2
            meas_rx = io[f"{hyb}_{peer}"]["rx_bytes_per_tx"][0] - io[f"{base}_{peer}"]["rx_bytes_per_tx"][0]
            # Eq. (rx-model) as printed: block + header copies + endorsed proposal (endorsers only)
            m_paper = d_blk + hdr_copies + (signed_req if endorser else 0)
            # + the signed DELIVER_SEEK_INFO envelope the CLI sends to every --peerAddresses peer per invoke
            m_ext = m_paper + (signed_req if endorser else 0)
            p["rx"][peer] = {"endorser": endorser, "measured": meas_rx,
                             "model_paper": m_paper, "ratio_paper": m_paper / meas_rx,
                             "model_with_deliver_req": m_ext, "ratio_with_deliver_req": m_ext / meas_rx,
                             "residual_with_deliver_req": meas_rx - m_ext,
                             "signature_field_only_ratio": d_sig / meas_rx}
        model["pairs"][f"{hyb}_vs_{base}"] = p
    # peer0-minus-peer1 rx gap (single endorsement): isolates what only the endorsing, client-facing peer receives
    g = {}
    for s in ("S1", "S2"):
        g[s] = io[f"{s}_peer0"]["rx_bytes_per_tx"][0] - io[f"{s}_peer1"]["rx_bytes_per_tx"][0]
    model["endorser_gap"] = {"S1": g["S1"], "S2": g["S2"], "growth": g["S2"] - g["S1"],
                             "one_signed_msg": signed_req, "two_signed_msgs": 2 * signed_req}

    res = {"blocks": summ, "objects": obj, "model": model}
    with open(os.path.join(out, "block_summary.json"), "w") as fh:
        json.dump(res, fh, indent=1)
    return res


if __name__ == "__main__":
    r = main(*sys.argv[1:4])
    for s, v in r["blocks"].items():
        print(s, v["blocks"], "blk %.1f±%.2f" % tuple(v["block"][:2]), "envsig %.2f" % v["env_sig"][0],
              "payload %.1f data %.1f meta %.1f hdr %.1f" % (v["payload"][0], v["data"][0], v["metadata"][0], v["header"][0]),
              "q", v["n_consenter_sig"][0], "cert %.1f" % v["creator_cert"][0])
    print(json.dumps(r["objects"], indent=0))
    print(json.dumps(r["model"], indent=1))
