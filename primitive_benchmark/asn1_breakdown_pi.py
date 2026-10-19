#!/usr/bin/env python3
"""asn1_breakdown_pi.py - measure hybrid ASN.1 encode/decode time only."""
import statistics
import time

ecdsa_der = b"\x30" + b"\x44" + b"\x02" * 70
mldsa_sig = b"\x00" * 2420


def hybrid_asn1_encode(ecdsa_der, mldsa_sig):
    n1 = len(ecdsa_der)
    n2 = len(mldsa_sig)
    # first INTEGER TLV
    inner1 = bytes([0x02]) + (bytes([0x81, n1]) if n1 >= 0x80 else bytes([n1])) + ecdsa_der
    # second INTEGER TLV
    inner2 = bytes([0x02, 0x82, (n2 >> 8) & 0xFF, n2 & 0xFF]) + mldsa_sig
    inner = inner1 + inner2
    total = len(inner)
    return bytes([0x30, 0x82, (total >> 8) & 0xFF, total & 0xFF]) + inner


def hybrid_asn1_decode(buf):
    assert buf[0] == 0x30
    if buf[1] == 0x82:
        pos = 4
    elif buf[1] == 0x81:
        pos = 3
    else:
        pos = 2
    # first INTEGER
    assert buf[pos] == 0x02
    pos += 1
    if buf[pos] == 0x81:
        first_len = buf[pos + 1]
        pos += 2
    else:
        first_len = buf[pos]
        pos += 1
    first = buf[pos:pos + first_len]
    pos += first_len
    # second INTEGER
    assert buf[pos] == 0x02
    pos += 1
    if buf[pos] == 0x82:
        second_len = (buf[pos + 1] << 8) | buf[pos + 2]
        pos += 3
    elif buf[pos] == 0x81:
        second_len = buf[pos + 1]
        pos += 2
    else:
        second_len = buf[pos]
        pos += 1
    second = buf[pos:pos + second_len]
    return first, second


for _ in range(50):
    buf = hybrid_asn1_encode(ecdsa_der, mldsa_sig)
    hybrid_asn1_decode(buf)

enc_times = []
dec_times = []
for _ in range(1000):
    t0 = time.perf_counter_ns()
    buf = hybrid_asn1_encode(ecdsa_der, mldsa_sig)
    t1 = time.perf_counter_ns()
    enc_times.append(t1 - t0)
    hybrid_asn1_decode(buf)
    t2 = time.perf_counter_ns()
    dec_times.append(t2 - t1)

print(f"t_asn1_enc = {statistics.mean(enc_times)/1e6:.4f} ms ± {statistics.pstdev(enc_times)/1e6:.4f} ms")
print(f"t_asn1_dec = {statistics.mean(dec_times)/1e6:.4f} ms ± {statistics.pstdev(dec_times)/1e6:.4f} ms")
print(f"t_asn1_total = {(statistics.mean(enc_times)+statistics.mean(dec_times))/1e6:.4f} ms")