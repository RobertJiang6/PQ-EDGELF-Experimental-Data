#!/usr/bin/env bash
# One closed-loop client: sends N CreateAsset invokes, each waiting for its commit event.
# Usage: client.sh <net> <mode> <client_id> <n_tx> <out_csv> <tag>
# Identical invoke for all scenarios (same business fields; key = fixed-length tag + counters).
source "$(dirname "$0")/env.sh"
NETA=$1; MODE=$2; CID=$3; N=$4; OUT=$5; TAG=$6
net_env "$NETA"
PEERS=(--peerAddresses "$P0" --tlsRootCertFiles "$P0_CA")
[ "$MODE" = peer0_peer1 ] && PEERS+=(--peerAddresses "$P1" --tlsRootCertFiles "$P1_CA")
echo "client_id,tx_index,tx_key,start_ms,end_ms,latency_ms,status,orderer,error" > "$OUT"
for i in $(seq 1 "$N"); do
  KEY="${TAG}_c$(printf %02d "$CID")_t$(printf %04d "$i")_$(date +%s%N)"
  ARGS="{\"Args\":[\"CreateAsset\",\"$KEY\",\"blue\",\"1\",\"owner\",\"10\"]}"
  S=$(now_ms)
  O=$(peer chaincode invoke -o "$ORD_ADDR" --ordererTLSHostnameOverride "$ORD_HOST" --tls --cafile "$ORD_CA" \
        -C mychannel -n basic "${PEERS[@]}" -c "$ARGS" --waitForEvent --waitForEventTimeout 60s 2>&1)
  RC=$?; E=$(now_ms); ERR=""
  if [ $RC -ne 0 ] || ! grep -q 'status:200' <<<"$O"; then [ $RC -eq 0 ] && RC=99; ERR=$(tr ',\n\r' ';  ' <<<"$O" | cut -c1-240); fi
  echo "$CID,$i,$KEY,$S,$E,$((E-S)),$RC,$LEADER,$ERR" >> "$OUT"
done
