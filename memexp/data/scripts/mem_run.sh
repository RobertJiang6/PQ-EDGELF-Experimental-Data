#!/usr/bin/env bash
# One memory run: restart both peers of the scenario's network (common starting point), idle,
# warm up, then a 1-client and a 16-client phase, with 2-s memory sampling on both peers.
# Usage: mem_run.sh <scen> <run_id>
# env:   MEM_IDLE_S (30)  MEM_WARM (100)  MEM_N1 (1000)  MEM_N16 (1000)
source "$(dirname "$0")/env.sh"
SC=$1; RUN=$2
IDLE=${MEM_IDLE_S:-30}; WARM=${MEM_WARM:-100}; N1=${MEM_N1:-1000}; N16=${MEM_N16:-1000}
NETA=$(scen_net $SC); MODE=$(scen_mode $SC)
D=$RES/$SC/$RUN
[ -f "$D/DONE" ] && { echo "skip $D (done)"; exit 0; }
[ -e "$D" ] && mv "$D" "$D.incomplete.$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$D/clients"
net_env "$NETA"
[ "$(cat $STATE/current_net 2>/dev/null)" = "$NETA" ] || { echo "network $NETA not active" >&2; exit 5; }
M=$D/run_meta.txt
{ echo "scenario=$SC"; echo "net=$NETA"; echo "endorsement=$MODE"; echo "run_id=$RUN"; echo "leader=$LEADER"
  echo "idle_s=$IDLE"; echo "warm_tx=$WARM"; echo "n_c1=$N1"; echo "n_c16=$N16"; } > "$M"
mark() { echo "$1=$(now_ms)" >> "$M"; }

# 1. restart both peers of the measured network
mark restart_ms
pi $PI0 "docker restart -t 20 $P0C >/dev/null" & pi $PI1 "docker restart -t 20 $P1C >/dev/null" & wait
ok=0
for t in $(seq 1 36); do
  sleep 5
  h0=$(chain_height "$P0" "$P0_CA"); h1=$(chain_height "$P1" "$P1_CA")
  if [ -n "$h0" ] && [ "$h0" = "$h1" ]; then ok=1; break; fi
done
[ $ok = 1 ] || { echo "peers not ready after restart (h0=$h0 h1=$h1)" >&2; exit 4; }
sleep 15
mark ready_ms; echo "height_ready=$h0" >> "$M"

# 2. samplers on both Pis
RP=$PI_REMOTE_DIR/collect/${SC}_${RUN}
for k in 0 1; do
  ip=$([ $k = 0 ] && echo $PI0 || echo $PI1); c=$([ $k = 0 ] && echo $P0C || echo $P1C)
  pi $ip "mkdir -p $PI_REMOTE_DIR/collect; nohup bash $PI_REMOTE_DIR/pi_memcollect.sh $c $MPORT ${RP}_peer$k.csv ${RP}_peer$k.stop 2 >/dev/null 2>&1 < /dev/null &"
done
mark idle_start_ms; sleep "$IDLE"; mark idle_end_ms

# 3. warm-up (excluded from the load phases)
mark warm_start_ms
bash "$SCRIPTS/client.sh" "$NETA" "$MODE" 1 "$WARM" "$D/warmup.csv" "${SC}mwu${RUN#run}"
mark warm_end_ms
echo "warm_ok=$(awk -F, 'NR>1 && $7==0' $D/warmup.csv | wc -l)" >> "$M"

# 4. load phases: exactly ntx transactions over conc closed-loop clients
phase() { # name conc ntx
  local name=$1 conc=$2 ntx=$3 base rem pids="" c n
  base=$((ntx / conc)); rem=$((ntx % conc))
  mark ${name}_start_ms
  for c in $(seq 1 "$conc"); do n=$base; [ "$c" -le "$rem" ] && n=$((n+1))
    bash "$SCRIPTS/client.sh" "$NETA" "$MODE" "$c" "$n" "$D/clients/${name}_client_$(printf %02d $c).csv" "${SC}m${name}${RUN#run}" &
    pids="$pids $!"
  done
  wait $pids
  mark ${name}_end_ms
  { echo "client_id,tx_index,tx_key,start_ms,end_ms,latency_ms,status,orderer,error"
    for f in "$D"/clients/${name}_client_*.csv; do tail -n +2 "$f"; done; } > "$D/${name}_latency.csv"
  echo "${name}_ok=$(awk -F, 'NR>1 && $7==0' $D/${name}_latency.csv | wc -l)" >> "$M"
}
phase c1 1 "$N1"
sleep 10
phase c16 16 "$N16"
sleep 10
mark tail_end_ms

# 5. stop samplers, fetch data, closing checks
pi $PI0 "touch ${RP}_peer0.stop"; pi $PI1 "touch ${RP}_peer1.stop"; sleep 4
pi_get $PI0 "${RP}_peer0.csv" "$D/mem_peer0.csv"; pi_get $PI1 "${RP}_peer1.csv" "$D/mem_peer1.csv"
echo "height_end_p0=$(chain_height $P0 $P0_CA)" >> "$M"; echo "height_end_p1=$(chain_height $P1 $P1_CA)" >> "$M"
echo "leader_after=$(detect_leader $NETA)" >> "$M"
for k in 0 1; do
  ip=$([ $k = 0 ] && echo $PI0 || echo $PI1)
  echo "pi${k}_end=\"$(pi $ip "echo temp_mC=\$(cat /sys/class/thermal/thermal_zone0/temp) throttled=\$(vcgencmd get_throttled | cut -d= -f2)")\"" >> "$M"
done
grep -E '^(warm|c1|c16)_ok' "$M" | tr '\n' ' ' > "$D/DONE"
echo "[done] mem $SC $RUN $(cat $D/DONE)"
