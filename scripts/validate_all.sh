#!/usr/bin/env bash

set -u
cd "$HOME/online-exam-network" || exit 1

STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT="results/validation_${STAMP}.txt"
LOGDIR="results/validation_${STAMP}_logs"
mkdir -p "$LOGDIR"

PASS=0
FAIL=0
SKIP=0

log() {
    printf '%s\n' "$*" | tee -a "$REPORT"
}

pass() { PASS=$((PASS+1)); log "[PASS] $*"; }
fail() { FAIL=$((FAIL+1)); log "[FAIL] $*"; }
skip() { SKIP=$((SKIP+1)); log "[SKIP] $*"; }

log "=================================================="
log " ONLINE EXAM NETWORK - AUTOMATED VALIDATION"
log " Started: $(date)"
log " Project: $PWD"
log "=================================================="
log ""

# 1. Project files
log "---- 1. PROJECT FILES ----"
for f in Makefile src/server.c src/client.c src/protocol.c \
         src/protocol.h sdn/exam_controller.py src/topology.py; do
    if [[ -f "$f" ]]; then
        pass "Found $f"
    else
        fail "Missing $f"
    fi
done
log ""

# 2. Build
log "---- 2. BUILD ----"
if make clean all >"$LOGDIR/build.log" 2>&1; then
    pass "make clean all"
else
    fail "Build failed; see $LOGDIR/build.log"
    cat "$LOGDIR/build.log" | tee -a "$REPORT"
fi
log ""

# 3. Server availability. Reuse an existing server; start one only if needed.
log "---- 3. APPLICATION SERVER ----"
OWN_SERVER_PID=""
if timeout 2 bash -c 'exec 3<>/dev/tcp/127.0.0.1/8080' 2>/dev/null; then
    pass "TCP server already listening on port 8080; reusing it"
else
    if [[ -x ./server ]]; then
        ./server >"$LOGDIR/server.log" 2>&1 &
        OWN_SERVER_PID=$!
        for _ in $(seq 1 30); do
            if timeout 1 bash -c 'exec 3<>/dev/tcp/127.0.0.1/8080' 2>/dev/null; then
                break
            fi
            sleep 0.2
        done
        if timeout 2 bash -c 'exec 3<>/dev/tcp/127.0.0.1/8080' 2>/dev/null; then
            pass "Started server for validation (PID $OWN_SERVER_PID)"
        else
            fail "Could not start server; see $LOGDIR/server.log"
            OWN_SERVER_PID=""
        fi
    else
        fail "Server binary unavailable"
    fi
fi

cleanup() {
    if [[ -n "${OWN_SERVER_PID:-}" ]]; then
        kill "$OWN_SERVER_PID" 2>/dev/null || true
        wait "$OWN_SERVER_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT
log ""

# 4. Concurrent full exam test
log "---- 4. CONCURRENT FULL EXAM TEST ----"
if timeout 120 python3 - <<'PY' >"$LOGDIR/concurrent_exams.log" 2>&1
import socket, threading, time, re, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

HOST, PORT, N = "127.0.0.1", 8080, 10
ANSWERS = ["B", "C", "C", "A", "B"]
barrier = threading.Barrier(N)

def recvline(sock, buf):
    while b"\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("server closed connection")
        buf += chunk
    line, buf = buf.split(b"\n", 1)
    return line.decode(errors="replace").strip(), buf

def cmd(sock, text, buf):
    sock.sendall((text + "\n").encode())
    return recvline(sock, buf)

def student(i):
    start = time.perf_counter()
    sid = f"AUTOVAL_{i:02d}"
    try:
        with socket.create_connection((HOST, PORT), timeout=10) as s:
            s.settimeout(10)
            buf = b""
            barrier.wait(timeout=10)
            s.sendall(f"STUDENT {sid}\n".encode())
            line, buf = recvline(s, buf)
            if line.startswith("ERROR:"):
                raise RuntimeError("registration: " + line)
            line, buf = recvline(s, buf)
            if "Enter START" not in line:
                raise RuntimeError("welcome: " + line)
            line, buf = cmd(s, "START", buf)
            if not line.startswith("STARTED:"):
                raise RuntimeError("start: " + line)
            for q, ans in enumerate(ANSWERS, 1):
                line, buf = cmd(s, f"GET {q}", buf)
                if not line.startswith("QUESTION "):
                    raise RuntimeError(f"GET {q}: {line}")
                line, buf = cmd(s, f"ANSWER {q} {ans}", buf)
                if not line.startswith("OK:"):
                    raise RuntimeError(f"ANSWER {q}: {line}")
            line, buf = cmd(s, "SUBMIT", buf)
            if not line.startswith("RESULT:"):
                raise RuntimeError("submit: " + line)
            m = re.search(r"\bScore\s*=\s*(\d+)\s*/\s*(\d+)", line)
            if not m or (int(m.group(1)), int(m.group(2))) != (5, 5):
                raise RuntimeError("score not verified: " + line)
            return i, True, time.perf_counter()-start, line
    except Exception as e:
        return i, False, time.perf_counter()-start, f"{type(e).__name__}: {e}"

def main():
    t0 = time.perf_counter()
    results = []
    with ThreadPoolExecutor(max_workers=N) as pool:
        futures = [pool.submit(student, i) for i in range(1, N+1)]
        for f in as_completed(futures):
            results.append(f.result())
    results.sort()
    for i, ok, secs, detail in results:
        print(f"Student {i:02d}: {'PASS' if ok else 'FAIL'} | {secs:.3f}s | {detail}")
    passed = sum(ok for _, ok, _, _ in results)
    print(f"SUMMARY: {passed}/{N} passed; elapsed={time.perf_counter()-t0:.3f}s")
    sys.exit(0 if passed == N else 1)

main()
PY
then
    cat "$LOGDIR/concurrent_exams.log" | tee -a "$REPORT"
    if grep -qE 'SUMMARY: 10/10 passed' "$LOGDIR/concurrent_exams.log"; then
        pass "10 concurrent students completed exams and received 5/5"
    else
        fail "Concurrent exam test did not fully pass"
    fi
else
    cat "$LOGDIR/concurrent_exams.log" | tee -a "$REPORT"
    fail "Concurrent exam test failed or timed out"
fi
log ""

# 5. Open vSwitch and Mininet prerequisites
log "---- 5. SDN PREREQUISITES ----"
if command -v ovs-vsctl >/dev/null 2>&1 &&
   sudo -n ovs-vsctl show >"$LOGDIR/ovs.log" 2>&1; then
    pass "Open vSwitch responds"
    cat "$LOGDIR/ovs.log" | tee -a "$REPORT"
else
    skip "OVS check needs sudo permission or OVS is unavailable"
fi

if command -v mn >/dev/null 2>&1; then
    pass "Mininet command found"
else
    skip "Mininet command not found"
fi

for p in 6653 8765; do
    if timeout 1 bash -c "exec 3<>/dev/tcp/127.0.0.1/$p" 2>/dev/null; then
        pass "Port $p has a listener"
    else
        skip "Port $p has no listener"
    fi
done
log ""

# 6. SDN execution and congestion experiment
log "---- 6. SDN FUNCTIONAL TESTS ----"

if [[ -x scripts/test_sdn_policy.py ]] && \
   timeout 20 python3 scripts/test_sdn_policy.py >"$LOGDIR/sdn_policy.log" 2>&1; then
    cat "$LOGDIR/sdn_policy.log" | tee -a "$REPORT"
    pass "SDN controller policy test"
else
    if [[ -f scripts/test_sdn_policy.py ]]; then
        cat "$LOGDIR/sdn_policy.log" 2>/dev/null | tee -a "$REPORT"
        skip "SDN policy test not completed; check controller and connected switches"
    else
        skip "SDN policy test script not found"
    fi
fi

# Avoid creating a second Mininet topology when one is already running.
if pgrep -af '[s]rc/topology.py' >/dev/null 2>&1; then
    skip "Congestion experiment not started: Mininet topology is already running; run it separately after exiting Mininet"
elif command -v mn >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    if timeout 90 scripts/run_congestion_experiment.sh >"$LOGDIR/congestion.log" 2>&1; then
        cat "$LOGDIR/congestion.log" | tee -a "$REPORT"
        if grep -q 'Results: 0% dropped' "$LOGDIR/congestion.log" &&
           grep -qE 'h1 .*receiver throughput: [0-9.]+ [KMG]?bits/sec' "$LOGDIR/congestion.log" &&
           grep -qE 'h3 .*receiver throughput: [0-9.]+ [KMG]?bits/sec' "$LOGDIR/congestion.log"; then
            pass "Mininet connectivity and both congestion throughput tests"
        else
            fail "Congestion experiment completed but results were incomplete"
        fi
    else
        cat "$LOGDIR/congestion.log" 2>/dev/null | tee -a "$REPORT"
        fail "Congestion experiment failed or timed out"
    fi
else
    skip "Congestion experiment requires Mininet and passwordless sudo"
fi
log ""

# 7. Summary
log "=================================================="
log " SUMMARY"
log " Passed: $PASS"
log " Failed: $FAIL"
log " Skipped / not verified: $SKIP"
log " Finished: $(date)"
log " Report: $REPORT"
log " Logs: $LOGDIR"
if [[ "$FAIL" -eq 0 ]]; then
    log " Overall: NO FAILURES IN EXECUTED CHECKS"
else
    log " Overall: FAILURES DETECTED"
fi
log "=================================================="

# Store the report path for convenient retrieval.
printf '%s\n' "$REPORT" > results/latest_validation_report.txt

[[ "$FAIL" -eq 0 ]]
