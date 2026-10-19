#!/usr/bin/env bash
# Runs ON a Raspberry Pi. Prints a key=value snapshot of host and container counters.
# Usage: pi_snap.sh <container> <metrics_port>
C=$1; MP=$2
echo "ts=$(date +%s%3N)"
echo "wlan0_rx=$(cat /sys/class/net/wlan0/statistics/rx_bytes)"
echo "wlan0_tx=$(cat /sys/class/net/wlan0/statistics/tx_bytes)"
echo "eth0_rx=$(cat /sys/class/net/eth0/statistics/rx_bytes 2>/dev/null)"
echo "eth0_tx=$(cat /sys/class/net/eth0/statistics/tx_bytes 2>/dev/null)"
echo "mmc_sectors_written=$(awk '{print $7}' /sys/block/mmcblk0/stat)"
echo "mmc_sectors_read=$(awk '{print $3}' /sys/block/mmcblk0/stat)"
PID=$(docker inspect -f '{{.State.Pid}}' "$C" 2>/dev/null)
if [ -n "$PID" ] && [ "$PID" -gt 0 ]; then
  G=/sys/fs/cgroup$(cut -d: -f3 /proc/$PID/cgroup)
  echo "cg_cpu_usec=$(awk '/^usage_usec/{print $2}' $G/cpu.stat)"
  echo "cg_io=\"$(tr '\n' ' ' < $G/io.stat)\""
  echo "cg_mem_current=$(cat $G/memory.current)"
fi
echo "docker_stats=\"$(docker stats --no-stream --format '{{.NetIO}} | {{.BlockIO}} | {{.MemUsage}}' "$C" 2>/dev/null)\""
curl -s --max-time 5 "http://localhost:$MP/metrics" | grep -E '^(endorser_proposals_received|endorser_successful_proposals|gossip_comm_messages_received|gossip_comm_messages_sent|ledger_block_processing_time_count)[ {]' | sed -E 's/\{[^}]*\}//; s/ /=/' | awk -F= '{a[$1]+=$2}END{for(k in a) printf "%s=%.0f\n",k,a[k]}'
echo "temp_mC=$(cat /sys/class/thermal/thermal_zone0/temp)"
echo "throttled=$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)"
echo "root_free_kb=$(df -k / | awk 'NR==2{print $4}')"
echo "load=\"$(cat /proc/loadavg)\""
