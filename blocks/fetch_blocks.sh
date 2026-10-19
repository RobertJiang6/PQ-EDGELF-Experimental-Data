#!/usr/bin/env bash
# Fetch 10 consecutive single-transaction blocks from the middle of every c=1 system run
# (block numbers height_p0_pre+500 .. +509) from orderer1 of the scenario's network.
# Usage: fetch_blocks.sh <block_plan.txt> <out_dir>
# Writes <out_dir>/<S>/<run>/<num>.block; skips blocks already fetched; never touches results/.
set -u
source /home/sspu/pqedgelf-rerun-20261016/scripts/env.sh
PLAN=$1; OUT=$2; OFF=${OFF:-500}; N=${N:-10}
mkdir -p "$OUT"
echo "fetch start $(date -u +%FT%TZ) off=$OFF n=$N" >> "$OUT/fetch.log"
while read -r S RUN H; do
  net_env "$(scen_net "$S")"
  d=$OUT/$S/$RUN; mkdir -p "$d"
  for k in $(seq 0 $((N-1))); do
    b=$((H+OFF+k)); f=$d/$b.block
    [ -s "$f" ] && continue
    if FABRIC_LOGGING_SPEC=ERROR peer channel fetch "$b" "$f.tmp" -o "$ORD_ADDR" --ordererTLSHostnameOverride "$ORD_HOST" \
         --tls --cafile "$ORD_CA" -c mychannel >/dev/null 2>"$d/$b.err"; then
      mv "$f.tmp" "$f"; rm -f "$d/$b.err"
    else echo "FAIL $S $RUN $b" >> "$OUT/fetch.log"; fi
  done
  echo "$S $RUN $(NET=; ls "$d"/*.block 2>/dev/null | wc -l) blocks via $ORD_ADDR" >> "$OUT/fetch.log"
done < "$PLAN"
echo "fetch end $(date -u +%FT%TZ)" >> "$OUT/fetch.log"
