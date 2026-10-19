#!/usr/bin/env bash
# Memory experiment driver (VM1, nohup). Idempotent: runs with DONE are skipped, so it can simply
# be started again after an interruption.
# Usage: mem_orchestrate.sh [plan_file]    plan lines: <scenario> <run_id>
source "$(dirname "$0")/env.sh"
PLAN=${1:-$W/plan.txt}
mkdir -p "$RES" "$STATE"
log "mem orchestrator start pid=$$ plan=$PLAN lines=$(grep -vc '^#' $PLAN)"
ensure_net() {
  local want=$1
  [ "$(cat $STATE/current_net 2>/dev/null)" = "$want" ] && return 0
  bash "$SCRIPTS/net_switch.sh" "$want" && return 0
  log "net_switch $want failed (rc=$?), retrying in 60 s"; sleep 60
  bash "$SCRIPTS/net_switch.sh" "$want"
}
disk_ok() {
  local f0 f1
  f0=$(pi $PI0 "df -k / | awk 'NR==2{print \$4}'"); f1=$(pi $PI1 "df -k / | awk 'NR==2{print \$4}'")
  echo "$(date -u +%FT%TZ) pi0_free_kb=$f0 pi1_free_kb=$f1" >> "$STATE/disk.log"
  [ "${f0:-0}" -gt 700000 ] && [ "${f1:-0}" -gt 700000 ]
}
grep -v '^#' "$PLAN" | while read -r SC RUN; do
  [ -z "$SC" ] && continue
  [ -f "$RES/$SC/$RUN/DONE" ] && continue
  date -u +%FT%TZ > "$STATE/heartbeat"
  ensure_net "$(scen_net $SC)" < /dev/null || { log "ABORT: cannot switch to $(scen_net $SC)"; exit 1; }
  disk_ok < /dev/null || { log "ABORT: Pi unreachable or disk below 700 MB ($(tail -1 $STATE/disk.log))"; exit 1; }
  log "begin mem $SC $RUN leader=$(cat $STATE/leader_$(scen_net $SC))"
  log "$(bash $SCRIPTS/mem_run.sh $SC $RUN < /dev/null 2>&1 | tail -1)"
  sleep 5
done
log "mem orchestrator finished"
