#!/usr/bin/env bash
# Writes the counterbalanced run plan. Columns: phase scenario concurrency run_id n_tx collect
#  system  : 5 rounds x S1-S4, 1 client, 1000 tx, no sampling   (rounds alternate S1 S3 S2 S4 / S4 S2 S3 S1)
#  resource: 5 rounds x S1-S4, 1 client, 1000 tx, 2-s sampling  (opposite alternation)
#  sweep   : 3 reps x c in {1,2,4,8,16} x S1-S4, 1000 tx, sampling (c order and network order alternate)
#  pprof   : peer0 under a 1-client load, 3 x 60 s profiles, S2 then S1
A="S1 S3 S2 S4"; B="S4 S2 S3 S1"
echo "# generated $(date -u +%FT%TZ)"
for r in 1 2 3 4 5; do o=$A; [ $((r%2)) = 0 ] && o=$B; for s in $o; do echo "system $s 1 run0$r 1000 0"; done; done
for r in 1 2 3 4 5; do o=$B; [ $((r%2)) = 0 ] && o=$A; for s in $o; do echo "resource $s 1 run0$r 1000 1"; done; done
for k in 1 2 3; do
  cs="1 2 4 8 16"; [ $k = 2 ] && cs="16 8 4 2 1"
  nets="clean hybrid"; [ $k = 2 ] && nets="hybrid clean"
  for n in $nets; do i=0
    for c in $cs; do
      if [ $n = clean ]; then p="S1 S3"; q="S3 S1"; else p="S2 S4"; q="S4 S2"; fi
      o=$p; [ $((i%2)) = 1 ] && o=$q
      for s in $o; do echo "sweep $s $c run0$k 1000 1"; done; i=$((i+1))
    done
  done
done
echo "pprof S2 1 run01 900 0"
echo "pprof S1 1 run01 900 0"
