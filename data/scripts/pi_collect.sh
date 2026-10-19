#!/usr/bin/env bash
# Runs ON a Raspberry Pi. Samples one peer container's cgroup every INTERVAL s until STOP exists.
# CPU% = delta(cpu.stat usage_usec)/delta(t) (percent of one core, as docker stats);
# docker-stats memory = memory.current - inactive_file.
# Usage: pi_collect.sh <container> <out_csv> <stop_file> [interval_s]
C=$1; OUT=$2; STOP=$3; IV=${4:-2}
PID=$(docker inspect -f '{{.State.Pid}}' "$C") || exit 1
[ "$PID" -gt 0 ] 2>/dev/null || { echo "container $C not running" >&2; exit 1; }
G=/sys/fs/cgroup$(cut -d: -f3 /proc/$PID/cgroup)
echo "ts_ms,cpu_usage_usec,mem_current,inactive_file,anon,file,pids,peer_rss_kb,temp_mC,cpu0_freq_khz,load1" > "$OUT"
rm -f "$STOP"
while [ ! -e "$STOP" ]; do
  ts=$(date +%s%3N)
  u=$(awk '/^usage_usec/{print $2}' "$G/cpu.stat")
  m=$(cat "$G/memory.current")
  ms=$(awk '/^inactive_file /{a=$2}/^anon /{b=$2}/^file /{c=$2}END{print a","b","c}' "$G/memory.stat")
  p=$(cat "$G/pids.current")
  r=$(awk '/^VmRSS/{print $2}' /proc/$PID/status 2>/dev/null)
  t=$(cat /sys/class/thermal/thermal_zone0/temp)
  f=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq)
  l=$(cut -d' ' -f1 /proc/loadavg)
  echo "$ts,$u,$m,$ms,$p,$r,$t,$f,$l" >> "$OUT"
  sleep "$IV"
done
