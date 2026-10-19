#!/usr/bin/env bash
# Make <net> the only Fabric network with running peers on the Pis (orderers are never touched).
# Usage: net_switch.sh clean|hybrid      exit 0 ok, 3 binary mismatch, 4 peers not ready
source "$(dirname "$0")/env.sh"
TARGET=$1
case $TARGET in clean) OTHER=hybrid; CC_OTHER=basic_1.0-; ;; hybrid) OTHER=clean; CC_OTHER=basic_cleanbatch01_; ;; *) exit 2;; esac
net_env "$OTHER"; O0=$P0C; O1=$P1C
net_env "$TARGET"; T0=$P0C; T1=$P1C
log "net_switch -> $TARGET"
pi $PI0 "docker stop -t 20 $O0 >/dev/null 2>&1; for c in \$(docker ps -q --filter name=dev-peer0.org1.example.com-$CC_OTHER); do docker stop -t 5 \$c >/dev/null; done; docker start $T0 >/dev/null" || true
pi $PI1 "docker stop -t 20 $O1 >/dev/null 2>&1; for c in \$(docker ps -q --filter name=dev-peer1.org1.example.com-$CC_OTHER); do docker stop -t 5 \$c >/dev/null; done; docker start $T1 >/dev/null" || true
ok=0
for t in $(seq 1 36); do
  sleep 5
  h0=$(chain_height "$P0" "$P0_CA"); h1=$(chain_height "$P1" "$P1_CA")
  if [ -n "$h0" ] && [ -n "$h1" ]; then ok=1; break; fi
done
[ $ok = 1 ] || { log "net_switch $TARGET: peers not ready (h0=$h0 h1=$h1)"; exit 4; }
sleep 15   # let gossip membership and deliver streams settle
want=$(eval echo \$WANT_PEER_$TARGET)
s0=$(pi $PI0 "docker exec $T0 sh -c 'sha256sum \$(readlink /proc/1/exe)' | cut -c1-16")
s1=$(pi $PI1 "docker exec $T1 sh -c 'sha256sum \$(readlink /proc/1/exe)' | cut -c1-16")
others=$(pi $PI0 "docker ps --format '{{.Names}}' | grep -cx -- '$O0'"; pi $PI1 "docker ps --format '{{.Names}}' | grep -cx -- '$O1'")
L=$(detect_leader "$TARGET"); echo "$L" > "$STATE/leader_$TARGET"
ordsha=""; [ "$TARGET" = hybrid ] && ordsha=$(docker exec orderer1.example.com sha256sum /fabric-bin/orderer | cut -c1-16)
echo "$TARGET" > "$STATE/current_net"
log "net_switch $TARGET ready: h0=$h0 h1=$h1 peer0=$s0 peer1=$s1 want=$want other_running=$(echo $others | tr '\n' ' ') leader=$L orderer1=$ordsha"
[ "$L" = 1 ] || log "WARNING: $TARGET SmartBFT leader is $L (clients will submit to orderer$L)"
if [ "$s0" != "$want" ] || [ "$s1" != "$want" ]; then log "ERROR binary mismatch"; exit 3; fi
if [ "$TARGET" = hybrid ] && [ "$ordsha" != "$WANT_ORDERER_hybrid" ]; then log "ERROR orderer binary mismatch"; exit 3; fi
exit 0
