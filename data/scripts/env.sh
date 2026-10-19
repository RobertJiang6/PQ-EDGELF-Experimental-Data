# Shared settings for the PQ-EDGELF full re-measurement (option C, 2026-10-16).
# Sourced by every script on VM1. Never writes results by itself.
W=${PQ_W:-/home/sspu/pqedgelf-rerun-20261016}
SCRIPTS=$W/scripts
RES=$W/results
STATE=$W/state
PI0=10.28.31.47
PI1=10.28.31.74
PI_SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o ServerAliveInterval=15 -o PubkeyAuthentication=no -o PreferredAuthentications=password"
PI_REMOTE_DIR=/home/jiangfei/pqedgelf-rerun-20261016${PQ_SMOKE:+-smoke}
# expected binaries (sha256 prefixes)
WANT_PEER_hybrid=79eff6a365a317ba   # lean = strict policy, diagnostics removed
WANT_PEER_clean=afea375a1e36792a    # stock Fabric 3.1.4 peer (ECDSA network)
WANT_ORDERER_hybrid=d7a90ad2afe13fe4

pi() { sshpass -p "$PI_PASS" ssh $PI_SSH_OPTS jiangfei@"$1" "$2"; }
pi_get() { sshpass -p "$PI_PASS" scp -q $PI_SSH_OPTS jiangfei@"$1":"$2" "$3"; }
now_ms() { date +%s%3N; }
log() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$W/orchestrator.log"; }

scen_net() { case $1 in S1|S3) echo clean;; S2|S4) echo hybrid;; esac; }
scen_mode() { case $1 in S1|S2) echo peer0_only;; S3|S4) echo peer0_peer1;; esac; }

net_env() {
  NET=$1
  case $NET in
    clean)  BIN=/home/sspu/fabric-3.1.4-clean/bin; LAB=/home/sspu/fabric-3.1.4-clean-lab; OPORT=8050; PPORT=8051
            ORD1C=clean-orderer1.example.com; P0C=clean-peer0.org1.example.com; P1C=clean-peer1.org1.example.com
            MPORT=10444; PPROF=6062 ;;
    hybrid) BIN=/home/sspu/fabric-3.1.4/bin; LAB=/home/sspu/fabric-3.1.4-lab; OPORT=7050; PPORT=7051
            ORD1C=orderer1.example.com; P0C=peer0.org1.example.com; P1C=peer1.org1.example.com
            MPORT=9444; PPROF=6060 ;;
    *) echo "net_env: bad net $NET" >&2; return 2 ;;
  esac
  export PATH=$BIN:/usr/local/bin:/usr/bin:/bin FABRIC_CFG_PATH=$LAB/config FABRIC_LOGGING_SPEC=INFO PQ_PROFILING=0
  export CORE_PEER_LOCALMSPID=Org1MSP CORE_PEER_TLS_ENABLED=true
  export CORE_PEER_MSPCONFIGPATH=$LAB/crypto-config/peerOrganizations/org1.example.com/users/User1@org1.example.com/msp
  LEADER=$(cat "$STATE/leader_$NET" 2>/dev/null || echo 1)
  case $LEADER in 1|2|3|4) ;; *) LEADER=1 ;; esac
  ORD_HOST=orderer$LEADER.example.com; ORD_ADDR=$ORD_HOST:$OPORT
  ORD_CA=$LAB/crypto-config/ordererOrganizations/example.com/orderers/$ORD_HOST/tls/ca.crt
  P0=peer0.org1.example.com:$PPORT; P1=peer1.org1.example.com:$PPORT
  P0_CA=$LAB/crypto-config/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt
  P1_CA=$LAB/crypto-config/peerOrganizations/org1.example.com/peers/peer1.org1.example.com/tls/ca.crt
  export CORE_PEER_ADDRESS=$P0 CORE_PEER_TLS_ROOTCERT_FILE=$P0_CA
}

# SmartBFT leader as seen by orderer1 since its last start (prints 1-4 or "unknown").
detect_leader() {
  net_env "$1"
  local st l
  st=$(docker inspect -f '{{.State.StartedAt}}' "$ORD1C")
  l=$(docker logs --since "$st" "$ORD1C" 2>&1 | grep 'ChangeRole' | tail -1 | grep -o 'current leader: [0-9]*' | grep -o '[0-9]*$')
  echo "${l:-unknown}"
}

chain_height() { # uses current net_env; peer address given as $1 $2(ca)
  CORE_PEER_ADDRESS=$1 CORE_PEER_TLS_ROOTCERT_FILE=$2 FABRIC_LOGGING_SPEC=ERROR \
    peer channel getinfo -c mychannel 2>/dev/null | grep -o '"height":[0-9]*' | grep -o '[0-9]*'
}
