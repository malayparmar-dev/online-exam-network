#!/usr/bin/env python3
import re
import subprocess
import time
from pathlib import Path

OUT = Path("results/congestion_test.txt")
SERVER_LOG = Path("results/iperf_server.log")
HOST = "10.0.0.10"
PORT = 5201

def run(args, timeout=30):
    return subprocess.run(
        args, capture_output=True, text=True, timeout=timeout
    )

def main():
    report = []
    def log(s):
        print(s)
        report.append(s)

    # Start iperf3 on the Mininet server host through the Mininet CLI.
    # This script uses the running Mininet CLI via its host namespace.
    log("Congestion test prerequisites")
    check = run(["pgrep", "-af", "iperf3"])
    log("Existing iperf3 processes: " + (check.stdout.strip() or "none"))

    log("")
    log("This script requires iperf3 to run inside Mininet's server namespace.")
    log("At the mininet> prompt in Terminal 1, run:")
    log("  server iperf3 -s -D")
    log("")
    log("Then rerun this script after the server is ready.")
    log("")
    log("To run the client from Mininet, use these commands at mininet>:")
    log("  h1 iperf3 -c 10.0.0.10 -p 5201 -t 10")
    log("  h3 iperf3 -c 10.0.0.10 -p 5201 -t 10")
    log("")
    log("The h1-to-server path crosses the 5 Mbps inter-switch link.")
    log("The h3-to-server path stays on switch s2.")
    log("Compare their measured throughput to evaluate the bottleneck.")
    OUT.write_text("\n".join(report) + "\n")

if __name__ == "__main__":
    main()
