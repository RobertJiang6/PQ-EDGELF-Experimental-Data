/*
 * mldsa_breakdown_c.c
 * ============================================================
 * 直接调用 liboqs 的 C API 测 ML-DSA-44 签名/验证时间。
 * 静态链接 /usr/local/lib/liboqs.a（树莓派 4B 已有静态库）。
 * 输出格式：每行 "trial,t_sig_ns,t_ver_ns"，最后 stdout 汇总。
 *
 * 注意：该版本的 liboqs 强制 verify 使用 context string。
 * Fabric PQ-EDGELF 用空 ctx_str 签名，所以 verify 也必须用空 ctx_str。
 *
 * 编译（在树莓派上）：
 *   gcc -O2 -I/usr/local/include mldsa_breakdown_c.c \
 *       /usr/local/lib/liboqs.a -lcrypto -lssl -o mldsa_breakdown_c
 *
 * 运行：
 *   ./mldsa_breakdown_c 1000 50 > mldsa_pi.csv
 */

#include <oqs/oqs.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static long long timespec_diff_ns(const struct timespec *a, const struct timespec *b) {
    return (long long)(b->tv_sec - a->tv_sec) * 1000000000LL +
           (long long)(b->tv_nsec - a->tv_nsec);
}

int main(int argc, char **argv) {
    int trials = 1000;
    int warmup = 50;
    if (argc > 1) trials = atoi(argv[1]);
    if (argc > 2) warmup = atoi(argv[2]);

    /* Initialize liboqs */
    OQS_init();

    const char *sig_name = "ML-DSA-44";
    OQS_SIG *sig = OQS_SIG_new(sig_name);
    if (sig == NULL) {
        fprintf(stderr, "ERROR: OQS_SIG_new(%s) returned NULL\n", sig_name);
        return 1;
    }

    /* Allocate keypair */
    size_t pk_len = sig->length_public_key;
    size_t sk_len = sig->length_secret_key;
    size_t sig_len_max = sig->length_signature;

    unsigned char *pk = malloc(pk_len);
    unsigned char *sk = malloc(sk_len);
    unsigned char *sig_buf = malloc(sig_len_max);

    if (!pk || !sk || !sig_buf) {
        fprintf(stderr, "ERROR: malloc failed\n");
        return 1;
    }

    /* Mock message: 64 B (matches Fabric proposal payload) */
    unsigned char msg[64];
    memset(msg, 0xab, sizeof(msg));

    /* Generate keypair once */
    OQS_STATUS rc = OQS_SIG_keypair(sig, pk, sk);
    if (rc != OQS_SUCCESS) {
        fprintf(stderr, "ERROR: OQS_SIG_keypair failed\n");
        return 1;
    }

    /* Warmup */
    size_t sig_len_actual;
    for (int i = 0; i < warmup; i++) {
        OQS_SIG_sign(sig, sig_buf, &sig_len_actual, msg, sizeof(msg), sk);
        OQS_SIG_verify_with_ctx_str(sig, msg, sizeof(msg), sig_buf,
                                     sig_len_actual, (const uint8_t *)"", 0, pk);
    }

    /* Measurement phase: emit CSV to stdout */
    printf("trial,t_sig_ns,t_ver_ns\n");
    struct timespec t0, t1, t2;
    int failures = 0;
    for (int i = 1; i <= trials; i++) {
        clock_gettime(CLOCK_MONOTONIC, &t0);
        OQS_STATUS sr = OQS_SIG_sign(sig, sig_buf, &sig_len_actual, msg, sizeof(msg), sk);
        clock_gettime(CLOCK_MONOTONIC, &t1);
        long long t_sig_ns = timespec_diff_ns(&t0, &t1);
        if (sr != OQS_SUCCESS) {
            failures++;
            fprintf(stderr, "[trial %d] sign rc=%d\n", i, sr);
            continue;
        }

        clock_gettime(CLOCK_MONOTONIC, &t1);
        OQS_STATUS vr = OQS_SIG_verify_with_ctx_str(sig, msg, sizeof(msg),
                                                      sig_buf, sig_len_actual,
                                                      (const uint8_t *)"", 0, pk);
        clock_gettime(CLOCK_MONOTONIC, &t2);
        long long t_ver_ns = timespec_diff_ns(&t1, &t2);
        if (vr != OQS_SUCCESS) {
            failures++;
            fprintf(stderr, "[trial %d] verify rc=%d\n", i, vr);
            continue;
        }

        printf("%d,%lld,%lld\n", i, t_sig_ns, t_ver_ns);

        if (i % 100 == 0) {
            fprintf(stderr, "[progress] %d/%d trials (failures=%d)\n",
                    i, trials, failures);
        }
    }

    /* Cleanup */
    free(pk);
    free(sk);
    free(sig_buf);
    OQS_SIG_free(sig);
    OQS_destroy();

    fprintf(stderr, "[done] %d trials, %d failures\n", trials, failures);
    return failures > 0 ? 1 : 0;
}