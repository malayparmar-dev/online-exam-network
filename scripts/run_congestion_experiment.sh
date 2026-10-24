#!/usr/bin/env bash
set -u

cd "$HOME/online-exam-network" || exit 1
mkdir -p results

STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT="results/congestion_${STAMP}.txt"
RAW="results/congestion_${STAMP}_raw.log"
PORT=5202

{
    echo "Online Examination Network - Congestion Experiment"
    echo "Date: $(date)"
    echo "Host links: 10 Mbps, 2 ms delay"
    echo "Inter-switch link: 5 Mbps, 5 ms delay"
    echo "iperf3 test port: $PORT"
    echo
} | tee "$REPORT"

echo "Starting experiment. Raw output: $RAW"

if ! sudo python3 src/topology.py >"$RAW" 2>&1 <<MININET_COMMANDS
pingall
server pkill -f "iperf3 -s.*5202" || true
server iperf3 -s -1 -p 5202 &
sh sleep 2
h1 iperf3 -c 10.0.0.10 -p 5202 -t 5
sh sleep 1
server iperf3 -s -1 -p 5202 &
sh sleep 2
h3 iperf3 -c 10.0.0.10 -p 5202 -t 5
exit
MININET_COMMANDS
then
    echo "[FAIL] Mininet experiment failed." | tee -a "$REPORT"
    tail -n 50 "$RAW" | tee -a "$REPORT"
    exit 1
fi

echo "[INFO] Mininet experiment process completed." | tee -a "$REPORT"

echo
echo "========== CONNECTIVITY ==========" | tee -a "$REPORT"
grep -E 'Results:|dropped' "$RAW" | tee -a "$REPORT" || true

echo
echo "========== THROUGHPUT ==========" | tee -a "$REPORT"

python3 - "$RAW" "$REPORT" <<'PY'
import re
import sys
from pathlib import Path

raw_path, report_path = map(Path, sys.argv[1:3])
raw = raw_path.read_text(errors="replace")

# Find each client connection and its following receiver summary.
connection_pattern = re.compile(
    r'local (10\.0\.0\.\d+) port \d+ connected to 10\.0\.0\.10 port \d+'
    r'(.*?)(?=iperf Done\.|mininet>|$)',
    re.S
)
receiver_pattern = re.compile(
    r'(?m)^\[\s*\d+\]\s+[\d.]+-[\d.]+\s+sec\s+'
    r'[\d.]+\s+\w+\s+([\d.]+)\s+([KMG]?bits/sec)\s+receiver\s*$'
)

results = {}
for match in connection_pattern.finditer(raw):
    client_ip, section = match.groups()
    receiver_matches = receiver_pattern.findall(section)
    if receiver_matches:
        results[client_ip] = receiver_matches[-1]

lines = []
for host, ip in (("h1", "10.0.0.1"), ("h3", "10.0.0.3")):
    if ip in results:
        value, unit = results[ip]
        line = f"{host} ({ip}) -> server receiver throughput: {value} {unit}"
    else:
        line = f"{host} ({ip}) -> result missing; inspect raw log"
    print(line)
    lines.append(line)

with report_path.open("a") as f:
    f.write("\n========== PARSED THROUGHPUT RESULTS ==========\n")
    f.write("\n".join(lines) + "\n")

if len(results.keys() & {"10.0.0.1", "10.0.0.3"}) != 2:
    print("ERROR: Could not extract both host results.")
    sys.exit(1)

print(f"Report saved to: {report_path}")
PY

STATUS=$?

echo
echo "Report: $REPORT"
echo "Raw log: $RAW"
exit "$STATUS"
