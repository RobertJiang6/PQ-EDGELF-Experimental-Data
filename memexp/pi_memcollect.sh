#!/usr/bin/env bash
# Runs ON a Raspberry Pi. Samples one peer's memory every IV s until STOP exists.
# Go runtime figures come from the peer's operations endpoint, so no memory cgroup is needed
# (pi2 has none); cgroup columns stay empty where the controller is missing.
# Usage: pi_memcollect.sh <container> <metrics_port> <out_csv> <stop_file> [interval_s]
C=$1; MP=$2; OUT=$3; STOP=$4; IV=${5:-2}
PID=$(docker inspect -f '{{.State.Pid}}' "$C") || exit 1
[ "$PID" -gt 0 ] 2>/dev/null || { echo "container $C not running" >&2; exit 1; }
G=/sys/fs/cgroup$(cut -d: -f3 /proc/$PID/cgroup)
echo "ts_ms,heap_alloc,heap_inuse,heap_sys,go_sys,process_rss,goroutines,ledger_blocks,cg_mem_current,cg_inactive_file,vmrss_kb,cpu_usage_usec" > "$OUT"
rm -f "$STOP"
while [ ! -e "$STOP" ]; do
  ts=$(date +%s%3N)
  m=$(curl -s --max-time 2 "http://localhost:$MP/metrics" | awk '
    /^go_memstats_heap_alloc_bytes /{a=$2} /^go_memstats_heap_inuse_bytes /{b=$2} /^go_memstats_heap_sys_bytes /{c=$2}
    /^go_memstats_sys_bytes /{d=$2} /^process_resident_memory_bytes /{e=$2} /^go_goroutines /{f=$2}
    /^ledger_block_processing_time_count/{g+=$2}
    END{printf "%.0f,%.0f,%.0f,%.0f,%.0f,%.0f,%.0f", a,b,c,d,e,f,g}')
  cm=$(cat "$G/memory.current" 2>/dev/null)
  ci=$(awk '/^inactive_file /{print $2}' "$G/memory.stat" 2>/dev/null)
  r=$(awk '/^VmRSS/{print $2}' /proc/$PID/status 2>/dev/null)
  u=$(awk '/^usage_usec/{print $2}' "$G/cpu.stat")
  echo "$ts,$m,$cm,$ci,$r,$u" >> "$OUT"
  sleep "$IV"
done
