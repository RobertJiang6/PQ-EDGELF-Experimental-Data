#!/usr/bin/env bash
# One measured run: <conc> closed-loop clients sending <ntx> transactions in total (remainder spread
# over the first clients so that exactly ntx are sent). Host/container snapshots on both Pis
# before/after; optional 2-s cgroup sampling on both peers.
# Usage: run_one.sh <phase> <scen> <conc> <run_id> <ntx> <collect 0|1>
# Output: $RES/<phase>/<scen>/c<conc>/<run_id>/ ; refuses to touch a completed run.
source "$(dirname "$0")/env.sh"
PHASE=$1; SC=$2; CONC=$3; RUN=$4; NTX=$5; COLLECT=$6
NETA=$(scen_net $SC); MODE=$(scen_mode $SC)
D=$RES/$PHASE/$SC/c$CONC/$RUN
if [ -f "$D/DONE" ]; then echo "skip $D (done)"; exit 0; fi
if [ -e "$D" ]; then mv "$D" "$D.incomplete.$(date -u +%Y%m%dT%H%M%SZ)"; fi
mkdir -p "$D/clients"
net_env "$NETA"
[ "$(cat $STATE/current_net 2>/dev/null)" = "$NETA" ] || { echo "network $NETA not active" >&2; exit 5; }
TAG=$(printf '%s%s%02d%s' "$SC" "$(echo $PHASE | cut -c1-3)" "$CONC" "$RUN")
{
  echo "phase=$PHASE"; echo "scenario=$SC"; echo "net=$NETA"; echo "endorsement=$MODE"; echo "concurrency=$CONC"
  echo "run_id=$RUN"; echo "tx_total=$NTX"; echo "collect=$COLLECT"; echo "tag=$TAG"
  echo "leader=$LEADER"; echo "orderer_target=$ORD_ADDR"
  echo "client_cli_sha256=$(sha256sum $BIN/peer | cut -c1-16)"
  echo "height_p0_pre=$(chain_height $P0 $P0_CA)"; echo "height_p1_pre=$(chain_height $P1 $P1_CA)"
} > "$D/run_meta.txt"
pi $PI0 "bash $PI_REMOTE_DIR/pi_snap.sh $P0C $MPORT" > "$D/snap_peer0_pre.txt" 2>/dev/null
pi $PI1 "bash $PI_REMOTE_DIR/pi_snap.sh $P1C $MPORT" > "$D/snap_peer1_pre.txt" 2>/dev/null
RP=$PI_REMOTE_DIR/collect/$(echo "$D" | sed "s#$RES/##; s#/#_#g")
if [ "$COLLECT" = 1 ]; then
  for k in 0 1; do ip=$([ $k = 0 ] && echo $PI0 || echo $PI1); c=$([ $k = 0 ] && echo $P0C || echo $P1C)
    pi $ip "mkdir -p $PI_REMOTE_DIR/collect; nohup bash $PI_REMOTE_DIR/pi_collect.sh $c ${RP}_peer$k.csv ${RP}_peer$k.stop 2 >/dev/null 2>&1 < /dev/null &"
  done
  sleep 5
fi
BASE=$((NTX / CONC)); REM=$((NTX % CONC))
START=$(now_ms); echo "start_utc=$(date -u +%FT%T.%3NZ)" >> "$D/run_meta.txt"; echo "workload_start_ms=$START" >> "$D/run_meta.txt"
pids=""
for c in $(seq 1 "$CONC"); do n=$BASE; [ "$c" -le "$REM" ] && n=$((n+1))
  bash "$SCRIPTS/client.sh" "$NETA" "$MODE" "$c" "$n" "$D/clients/client_$(printf %02d $c).csv" "$TAG" &
  pids="$pids $!"
done
( while sleep 60; do n=$(cat "$D"/clients/*.csv 2>/dev/null | grep -vc '^client_id'); echo "[$(date -u +%T)] $n/$NTX" >> "$D/progress.log"; done ) > /dev/null 2>&1 & mon=$!
wait $pids
END=$(now_ms); kill $mon 2>/dev/null
{ echo "workload_end_ms=$END"; echo "end_utc=$(date -u +%FT%T.%3NZ)"; echo "duration_ms=$((END-START))"; } >> "$D/run_meta.txt"
sleep 3
if [ "$COLLECT" = 1 ]; then
  pi $PI0 "touch ${RP}_peer0.stop"; pi $PI1 "touch ${RP}_peer1.stop"; sleep 3
  pi_get $PI0 "${RP}_peer0.csv" "$D/resource_peer0.csv"; pi_get $PI1 "${RP}_peer1.csv" "$D/resource_peer1.csv"
fi
pi $PI0 "bash $PI_REMOTE_DIR/pi_snap.sh $P0C $MPORT" > "$D/snap_peer0_post.txt" 2>/dev/null
pi $PI1 "bash $PI_REMOTE_DIR/pi_snap.sh $P1C $MPORT" > "$D/snap_peer1_post.txt" 2>/dev/null
{ echo "height_p0_post=$(chain_height $P0 $P0_CA)"; echo "height_p1_post=$(chain_height $P1 $P1_CA)"; } >> "$D/run_meta.txt"
# merge client files
{ echo "client_id,tx_index,tx_key,start_ms,end_ms,latency_ms,status,orderer,error"; for f in "$D"/clients/*.csv; do tail -n +2 "$f"; done; } > "$D/invoke_latency.csv"
ok=$(awk -F, 'NR>1 && $7==0' "$D/invoke_latency.csv" | wc -l); all=$(($(wc -l < "$D/invoke_latency.csv")-1))
echo "sent=$all" >> "$D/run_meta.txt"; echo "ok=$ok" >> "$D/run_meta.txt"; echo "fail=$((all-ok))" >> "$D/run_meta.txt"
echo "leader_after=$(detect_leader $NETA)" >> "$D/run_meta.txt"
echo "ok=$ok sent=$all" > "$D/DONE"
echo "[done] $PHASE $SC c=$CONC $RUN ok=$ok/$all duration_ms=$((END-START))"
