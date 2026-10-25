# Demo and Verification Playbook

This is the standalone operator's guide for setting up the project, demonstrating each meaningful behavior, and running its automated counterpart. Follow the sections in order for a full demonstration, or use the feature map to jump to a specific capability.

## Verification status of this guide

- **Loopback exam walkthrough and raw TCP sequence: exercised.** On 2026-10-25, the documented `run_app.sh` server/client commands were run with a separate test port. The client started an exam, changed question 1 from A to B, submitted, and received `Score=1/5`. The raw `nc` sequence was also run with the full set of lines piped together; it returned the expected welcome, question, answer error, and `Score=1/5` result.
- **Automated Mininet counterpart: passed.** `results/network_validation_20261025_150625.txt` records the full topology, exam TCP, SDN policy, congestion, RTT, fairness, and recovery run.
- **Interactive Mininet xterm launch and student login: verified by the user.** On 2026-10-25, the user confirmed that `xterm h1 h2` opened both client windows and that student login worked. The remaining interactive steps in this playbook—including changing/navigation/submission, simultaneous exam completion, and manual SDN blocking/recovery—have not yet been confirmed. The automated Mininet run covers related application and policy behavior, but does not substitute for those manual checks.
- **Fresh Ubuntu bootstrap: not run in a clean VM.** The package and venv instructions were reviewed against the project scripts and CI setup, but this machine already had the project dependencies installed.

## 1. Fresh Ubuntu setup

Use Ubuntu with a graphical desktop for the interactive `xterm` demonstration. The automated application/controller tests can run without a graphical desktop. The full network experiment and live Mininet demo require sudo access.

### Install system tools

```bash
sudo apt update
sudo apt install build-essential mininet openvswitch-switch python3 python3-venv iperf3 netcat-openbsd xterm
sudo systemctl start openvswitch-switch
```

Check the main tools and service:

```bash
gcc --version
make --version
python3 --version
mn --version
ovs-vsctl --version
iperf3 --version
systemctl is-active openvswitch-switch
```

Clone the maintained repository, install the pinned OS-Ken environment, and build:

```bash
git clone https://github.com/malayparmar-dev/online-exam-network.git
cd online-exam-network
python3 -m venv .venv-sdn
.venv-sdn/bin/python -m pip install --upgrade pip
.venv-sdn/bin/python -m pip install -r requirements-sdn.txt
make
```

Run the non-privileged tests and isolated controller test before the demo:

```bash
make test
make test-controller
```

`make test-controller` requires `.venv-sdn` but does not need Mininet. The main CI workflow runs `make test`, Python syntax checks, pinned dependency installation, and `make test-controller` on Ubuntu 24.04. It does not run Mininet.

## 2. Start the interactive Mininet demo

Use three ordinary terminal windows on the Ubuntu desktop.

### Terminal 1 — controller

From the repository root:

```bash
./scripts/start_controller.sh
```

Leave this terminal open. It listens for OpenFlow on port 6653 and control commands on port 8765.

### Terminal 2 — topology

```bash
./scripts/start_topology.sh
```

At `mininet>`, check that all hosts can communicate:

```text
pingall
```

Expected: `0% dropped`. The topology has h1/h2 on s1, h3/server on s2, and a 5 Mbps shared inter-switch link.

Start the examination server in the Mininet CLI background:

```text
server ./server > /tmp/exam-server-demo.log 2>&1 &
```

### Terminal 3 — controller commands and logs

Use an ordinary Ubuntu shell at the repository root. Check controller status:

```bash
printf 'STATUS\n' | nc 127.0.0.1 8765
```

Expected fields include two connected switches, active/automatic block lists, a 2-second statistics interval, and the 5,000 packets/s threshold.

## 3. Demonstrate the exam application

At `mininet>`, open interactive shells for two hosts:

```text
xterm h1 h2
```

In each xterm, start the real C client:

```bash
./client 10.0.0.10
```

Use different student IDs. Type `START`; on question 1, answer `A` and then change it to `B`. This question's correct answer is B, so the final result should include one point. Demonstrate navigation with `N`, `P`, and a question number, then submit with `S` followed by `YES`. Each client should display its own result. Run both clients at once to demonstrate separate concurrent sessions. To demonstrate abandonment, start another attempt and enter `Q`; the client should show `QUIT: Examination abandoned.` and no score.

While one session remains active, open another host terminal and reuse its student ID. The server should reject the duplicate active ID. Then finish the original session.

To demonstrate that a stalled handshake does not block new clients, open another shell on the Mininet `server` host with `xterm server`, run `nc 127.0.0.1 8080`, and leave it connected without typing a student ID. Start and complete an exam from h3's xterm. Close the idle `nc` connection with Ctrl+C.

To inspect the application event log from Terminal 3:

```bash
tail -n 20 results/app_metrics.csv
```

Expected event types include `connected`, `started`, `question`, `answer`, `submitted`, and `disconnected`.

### Optional raw TCP protocol demonstration

This lets you show the text protocol without the client UI. Start a loopback server in a terminal:

```bash
EXAM_PORT=18081 EXAM_DURATION_SECONDS=60 EXAM_METRICS_FILE=/tmp/exam-raw-demo.csv ./scripts/run_app.sh server
```

In another terminal, connect and type each line after the previous response:

```bash
nc 127.0.0.1 18081
```

```text
STUDENT raw_demo
START
GET 1
ANSWER 1 B
ANSWER 2 Z
SUBMIT
```

Expect the server to send `WELCOME`, `STARTED`, a question, an answer-accepted response, `ERROR: Invalid command or question number.`, then a result with `Score=1/5`. Close the server with Ctrl+C. Fragmented TCP writes, CRLF handling, oversized-line recovery, and the deadline edge cases are more reliably demonstrated by the protocol/application automated tests.

### Optional short timer demonstration

The default exam timer is 300 seconds. For a short timer demonstration, first stop the normal exam server and close its clients, then start a local loopback server on a dedicated port:

```bash
EXAM_PORT=18080 EXAM_DURATION_SECONDS=15 EXAM_METRICS_FILE=/tmp/exam-timer-demo.csv ./scripts/run_app.sh server
```

In another terminal:

```bash
./scripts/run_app.sh client 127.0.0.1 18080
```

Enter an ID and start the exam. Wait longer than 15 seconds, then enter `N`. The server should finalize and return a `TIMEOUT` result. The client does not display a live countdown; the deadline and score are server-enforced. For an automatic, repeatable timeout test, use `make test`.

## 4. Demonstrate controller policy manually

With the Mininet topology still running, use Terminal 3 to test input validation and server protection:

```bash
printf 'BLOCK invalid\n' | nc 127.0.0.1 8765
printf 'BLOCK 10.0.0.10\n' | nc 127.0.0.1 8765
```

Both should return an error: the first is not an IPv4 address, and the second is the protected exam server.

Block h1:

```bash
printf 'BLOCK 10.0.0.1\n' | nc 127.0.0.1 8765
```

At `mininet>` compare h1 and h2:

```text
h1 ping -c 2 -W 1 10.0.0.10
h2 ping -c 2 -W 1 10.0.0.10
```

h1 should lose connectivity; h2 should remain connected. In h1's xterm, a bounded TCP connection attempt can show the exam service is inaccessible while blocked:

```bash
timeout 5 ./client 10.0.0.10
```

Enter a student ID if prompted. Since the controller drops h1's packets, the client should fail to connect before `timeout` expires. Unblock from Terminal 3:

```bash
printf 'UNBLOCK 10.0.0.1\n' | nc 127.0.0.1 8765
```

Repeat h1's ping and client command. h1 should recover. The full automated test also verifies an h2 exam succeeds while h1 is blocked and an h1 exam succeeds after recovery.

## 5. Demonstrate automatic blocking

Do this on a fresh topology or after clearing any previous h1 block. Start a one-test UDP receiver on the Mininet server:

```text
server iperf3 -s -1 -p 5203 > /tmp/exam-udp-server.log 2>&1 &
```

In h1's xterm, run the controlled high-rate UDP source:

```bash
iperf3 -c 10.0.0.10 -p 5203 -u -b 20M -l 64 -t 12
```

While it runs, query `STATUS` from Terminal 3 until `Automatically blocked IPs: 10.0.0.1` appears. h1's traffic should be blocked, while h2 remains usable. Let the 12-second source finish before unblocking; otherwise continuing high-rate packets can trigger the policy again. After it ends, wait about 3 seconds and send `UNBLOCK 10.0.0.1`, then verify h1 recovers.

For repeatable automatic-block, unaffected-client, exam-TCP denial, and recovery checks, use the automated full network validation in Section 7.

## 6. Measure congestion, response time, and fairness manually

Run this after clearing blocks. Start two `iperf3` servers from `mininet>` on separate ports:

```text
server iperf3 -s -p 5202 > /tmp/iperf-5202.log 2>&1 &
server iperf3 -s -p 5204 > /tmp/iperf-5204.log 2>&1 &
```

Measure h1's baseline RTT and cross-switch throughput, then h3's same-switch throughput:

```text
h1 ping -n -q -i 0.2 -c 10 10.0.0.10
h1 iperf3 -c 10.0.0.10 -p 5202 -t 6
h3 iperf3 -c 10.0.0.10 -p 5202 -t 6
```

To compare h1 and h2 fairly, open h1 and h2 terminals and start these 6-second transfers at nearly the same time:

```bash
# h1 terminal
iperf3 -c 10.0.0.10 -p 5202 -t 6 -J > /tmp/exam-h1-load.json &
load_pid=$!
ping -n -q -i 0.2 -c 30 10.0.0.10
wait "$load_pid"
```

```bash
# h2 terminal, start at the same time as the h1 commands
iperf3 -c 10.0.0.10 -p 5204 -t 6 -J
```

Compare h1/h2 receiver throughputs from the JSON `end.sum_received.bits_per_second` values. Calculate Jain's fairness index by substituting the two rates in Mbps:

```bash
python3 -c 'import sys; r=list(map(float,sys.argv[1:])); print(sum(r)**2/(len(r)*sum(x*x for x in r)))' H1_MBPS H2_MBPS
```

Replace `H1_MBPS` and `H2_MBPS` with numbers, for example `2.25 2.25`; an index of 1 means equal measured rates. Compare the average RTT printed by `ping` at baseline and during the two transfers. The automated experiment synchronizes and repeats these measurements three times; use it for the reproducible values in the report.

## 7. Automated counterpart for every feature

Run these commands from the repository root:

| Feature or behavior | Manual demonstration | Automated counterpart and expected evidence |
|---|---|---|
| Fresh setup and build | Install packages, create `.venv-sdn`, run `make` | GitHub Actions installs build/controller dependencies; `make test` builds with warning flags |
| TCP protocol flow, framing, and oversized input | Use the raw `nc` session above for the command/response sequence | `build/test_protocol` and application oversized-command test cover fragments, CRLF, buffering, rejection, and recovery |
| Questions, navigation, answer changes, validation, scoring, quit | Use the C client; navigate with N/P/number, change Q1 from A to B, submit; use Q in a separate attempt | `make test` checks all questions, navigation and invalid command handling, answer replacement, invalid answer, score, submit flow, and quit-without-result |
| Independent concurrent sessions and slow handshakes | Run h1/h2 xterms at once; try a duplicate active ID. Optional: leave an `nc` connection to the server idle before entering an ID, then start another client | `make test` checks ten concurrent isolated sessions, duplicate ID rejection, and that a stalled handshake does not block another client |
| Timer | Use the 15-second loopback procedure above and request another question after expiry | `make test` waits past the deadline and verifies timeout result, score, close, and one-time finalization |
| Application event metrics | Inspect `results/app_metrics.csv` with `tail` | Application acceptance test verifies UTC CSV fields and start/answer/submit/timeout events |
| Controller status and manual policy | Run `STATUS`, invalid/server `BLOCK`, valid `BLOCK`, `UNBLOCK`; compare host connectivity | `make test-controller` checks status, fragmented command, invalid/protected IP, and block/unblock; Mininet test checks forwarding effect |
| Automatic traffic block and recovery | Generate the 12-second h1 UDP source and poll `STATUS` | `scripts/run_network_validation.sh` requires automatic block, denies blocked h1 TCP, keeps h2 working, then verifies h1 recovery |
| Mininet topology/connectivity | `pingall`; inspect h1/h2/h3/server and s1/s2 | Network batch requires two connected switches and 12/12 successful pings |
| Throughput/congestion | Run baseline and concurrent `iperf3` commands above | Network batch records repeated cross/same-switch rates and simultaneous h1/h2 rates |
| Response time/fairness | Compare baseline/loaded ping RTT and compute Jain index | Network batch records baseline/loaded h1 RTT and three fairness indices in `PERFORMANCE_JSON` |
| Cleanup/results | Exit Mininet, close clients, Ctrl+C controller | Batch runner cleans its processes/topology and writes a dated summary report |

Run the full automated path with sudo authenticated in the same terminal:

```bash
sudo -v
./scripts/run_network_validation.sh
```

The latest verified report is `results/network_validation_20261025_150625.txt`. A new run writes a new report; compare only results from compatible environment/topology settings.

## 8. Close the demo cleanly

Close all client xterms. At `mininet>`, enter `exit`. Stop the controller in Terminal 1 with Ctrl+C. The automated runner manages its own topology and processes. Avoid broad `killall` commands; they can stop unrelated user processes.

## 9. Known scope limits

- The interactive Mininet xterm sequence must be rehearsed on the actual presentation machine; xterm, a working desktop display, Mininet, OVS, and sudo are prerequisites.
- The timer is server-enforced; the client has no continuously updating countdown display.
- The fairness index compares only the two measured TCP flows in this lab topology. It is not a general fairness guarantee.
- The recorded RTT values are ICMP network round-trip times, not application command latency.
- Student IDs are not authentication, and the packet-rate policy may block legitimate high-rate traffic.
