# Manual Live Demonstration Runbook

This is the hands-on demonstration guide for the Online Examination Network. It uses the actual application, Mininet CLI, host terminals, `iperf3`, `ping`, `nc`, and controller commands. It does not use the automated network-validation runner to demonstrate features.

## Verification record

- The user confirmed on 2026-10-29 that `xterm h1 h2` opens two client windows and that student login works.
- On 2026-10-29, the documented loopback client sequence was run on port 18391: login, start, answer replacement, next/previous/direct navigation, and submit completed with `Score=1/5`. The raw TCP sequence on port 18081 returned the expected invalid-command response and `Score=1/5`; the 15-second timer flow on port 18080 returned a `TIMEOUT` result after the next-question request.
- On 2026-10-29, `make test` passed (protocol, 5 performance metric tests, and 10 application tests), and `make test-controller` passed. All 26 Bash command blocks in this document passed `bash -n`; relative Markdown links and `git diff --check` also passed.
- Other loopback protocol flow evidence is also recorded in [the verification playbook](demo-and-verification-playbook.md).
- The remaining interactive Mininet sequences in this runbook have not yet been rehearsed end to end in this session. `xterm`, `mn`, and `ovs-vsctl` are present and `DISPLAY` is set, but `sudo -n true` reports that interactive authentication is required. The commands below are checked against the current topology, controller, and application source; Mininet steps must be run in an authenticated desktop terminal before they can be marked manually verified.
- The clean Ubuntu installation section is a procedure, not a claim that a fresh VM was provisioned here.

## 1. Prepare Ubuntu and the project [fresh Ubuntu setup not verified]

Use an Ubuntu desktop session for xterm and an account that can run Mininet with `sudo`. Install the system packages:

```bash
sudo apt update
sudo apt install build-essential mininet openvswitch-switch python3 python3-venv iperf3 netcat-openbsd xterm
sudo systemctl start openvswitch-switch
```

Check the required tools:

```bash
gcc --version
make --version
python3 --version
mn --version
ovs-vsctl --version
iperf3 --version
xterm -version
systemctl is-active openvswitch-switch
```

If this is a fresh machine, clone the repository once:

```bash
git clone https://github.com/malayparmar-dev/online-exam-network.git ~/online-exam-network
```

If the repository already exists, skip the clone. In either case, prepare and build it:

```bash
cd ~/online-exam-network
python3 -m venv .venv-sdn
.venv-sdn/bin/python -m pip install --upgrade pip
.venv-sdn/bin/python -m pip install -r requirements-sdn.txt
make
```

The automated checks are separate from the manual demonstrations. Run them if asked to show test evidence:

```bash
cd ~/online-exam-network
make test
make test-controller
```

The full Mininet validation is also automated. This runbook does not use it as a substitute for manually demonstrating the features.

## 2. Start the controller and live topology [partially verified: xterm launch and student login only]

Open three ordinary terminal windows. In each, the repository root is `~/online-exam-network`.

### Terminal 1: SDN controller

```bash
cd ~/online-exam-network
.venv-sdn/bin/osken-manager --ofp-tcp-listen-port 6653 sdn/exam_controller.py
```

Leave this running. It provides OpenFlow on TCP port 6653 and the local control interface on TCP port 8765.

### Terminal 2: Mininet topology

```bash
cd ~/online-exam-network
sudo --preserve-env=EXAM_OPENFLOW_PORT,EXAM_CONTROL_PORT python3 src/topology.py
```

Enter your sudo password when prompted. Wait for the `mininet>` prompt, then:

```text
pingall
```

Expected: all 12 host-to-host pings succeed (0% dropped). The lab has h1/h2 on s1, h3/server on s2, and a 5 Mbps inter-switch link.

Start the real exam server inside the Mininet `server` host:

```text
server ./server > /tmp/exam-server-demo.log 2>&1 &
```

### Terminal 3: controller control and evidence

```bash
cd ~/online-exam-network
printf 'STATUS\n' | nc 127.0.0.1 8765
```

Expected: `Connected switches: 2`, no blocked IPs, the configured packet-rate threshold, and the protected server IP `10.0.0.10`.

## 3. Demonstrate exam questions, answer changes, navigation, score, and quit [Mininet flow partly verified: xterm launch and login only]

At `mininet>`, open two client terminals:

```text
xterm h1 h2
```

In each xterm, the shell inherits the project working directory used to start Mininet (this matches the already verified `./client` launch). Confirm with `pwd` and `ls -l ./client`, then start the C client:

```bash
./client 10.0.0.10
```

In the h1 window, enter a student ID such as `demo_h1`, then type `START` when prompted. The client displays the current question and commands. To demonstrate answer replacement and navigation, enter these commands one at a time:

```text
A
B
N
P
5
1
S
YES
```

Question 1's correct answer is B. The result should show `Score=1/5`; it should count the final B answer, not the replaced A. The `N`, `P`, and number commands demonstrate forward, backward, and direct question navigation. `S` asks whether to submit; confirm with `YES`.

In h2, use a different ID such as `demo_h2`, start an exam, and submit it while h1 has an active session to demonstrate concurrent clients. Each client should receive its own result.

To demonstrate abandonment, start a new session and enter `Q` at the question prompt. Expected: `QUIT: Examination abandoned.` and no score is submitted.

To demonstrate duplicate active-ID rejection, leave one session open after login. In another client window, enter the same ID. Expected: an `ERROR` response saying the student already has an active session. Finish or quit the first session afterward.

### Slow handshake demonstration (optional)

At `mininet>`, open a shell on the exam server host:

```text
xterm server
```

In that xterm:

```bash
nc 127.0.0.1 8080
```

Leave the connection open without typing an ID. Back in `mininet>`, open another client on h3 and complete an exam:

```text
xterm h3
```

In the h3 xterm, run `./client 10.0.0.10`, then log in and complete an exam. It should complete while the idle connection remains open. Stop the idle `nc` with Ctrl+C.

### Show application event records

In Terminal 3:

```bash
tail -n 20 ~/online-exam-network/results/app_metrics.csv
```

Look for `connected`, `started`, `question`, `answer`, `submitted` or `disconnected` events from the IDs you used.

## 4. Demonstrate the text TCP protocol directly

This optional demonstration runs a local server outside Mininet. Use two ordinary terminals.

### Terminal A: local server

```bash
cd ~/online-exam-network
EXAM_PORT=18081 EXAM_DURATION_SECONDS=60 EXAM_METRICS_FILE=/tmp/exam-raw-demo.csv ./scripts/run_app.sh server
```

### Terminal B: raw TCP client

```bash
nc 127.0.0.1 18081
```

Type each line and wait for the response before entering the next:

```text
STUDENT raw_demo
START
GET 1
ANSWER 1 B
ANSWER 2 Z
SUBMIT
```

Expected responses include `WELCOME`, `STARTED`, a `QUESTION`, accepted answer feedback, `ERROR: Invalid command or question number.`, and a final `Score=1/5` result. Stop the server with Ctrl+C.

## 5. Demonstrate the server-enforced timer

Use a separate loopback server on port 18080. Stop any other server using that port first.

### Terminal A: 15-second exam server

```bash
cd ~/online-exam-network
EXAM_PORT=18080 EXAM_DURATION_SECONDS=15 EXAM_METRICS_FILE=/tmp/exam-timer-demo.csv ./scripts/run_app.sh server
```

### Terminal B: client

```bash
cd ~/online-exam-network
./scripts/run_app.sh client 127.0.0.1 18080
```

Enter a student ID and start the exam. Wait at least 16 seconds, then request another question with `N`. The server should finalize the exam and return a `TIMEOUT` result. The timer is enforced by the server; the client does not show a live countdown. Stop the server with Ctrl+C.

## 6. Demonstrate manual SDN block, isolation, and recovery [not yet manually verified]

Keep the controller, Mininet topology, and exam server running. In Terminal 3, first verify status and that invalid/protected addresses are rejected:

```bash
printf 'STATUS\n' | nc 127.0.0.1 8765
printf 'BLOCK invalid\n' | nc 127.0.0.1 8765
printf 'BLOCK 10.0.0.10\n' | nc 127.0.0.1 8765
```

The last two commands should return errors: `invalid` is not an IPv4 address, and `10.0.0.10` is the protected exam server.

Block h1 from Terminal 3:

```bash
printf 'BLOCK 10.0.0.1\n' | nc 127.0.0.1 8765
```

Expected: `OK: Blocked 10.0.0.1`. At `mininet>`, compare h1 and h2:

```text
h1 ping -c 2 -W 1 10.0.0.10
h2 ping -c 2 -W 1 10.0.0.10
```

h1 should lose connectivity, while h2 should still reach the server. To show h1's exam TCP session is also denied, use the h1 xterm:

```bash
timeout 5 ./client 10.0.0.10
```

Enter a student ID if prompted; the connection should fail while h1 is blocked.

Unblock h1 from Terminal 3:

```bash
printf 'UNBLOCK 10.0.0.1\n' | nc 127.0.0.1 8765
```

Expected: `OK: Unblocked 10.0.0.1`. Repeat the h1 ping and client command; h1 should reach the server and be able to complete an exam again.

## 7. Demonstrate automatic blocking from generated traffic [not yet manually verified]

Start from a clean policy state. In Terminal 3, clear any earlier block and check `STATUS`; confirm h1 is not listed as blocked:

```bash
printf 'UNBLOCK 10.0.0.1\n' | nc 127.0.0.1 8765
printf 'STATUS\n' | nc 127.0.0.1 8765
```

Start a one-shot UDP receiver on the Mininet server host from `mininet>`:

```text
server iperf3 -s -1 -p 5203 > /tmp/exam-udp-server.log 2>&1 &
```

In the h1 xterm, generate 12 seconds of high-rate UDP traffic toward the exam server host:

```bash
iperf3 -c 10.0.0.10 -p 5203 -u -b 20M -l 64 -t 12
```

While it runs, repeatedly check controller status from Terminal 3:

```bash
printf 'STATUS\n' | nc 127.0.0.1 8765
```

Expected: `Automatically blocked IPs: 10.0.0.1`. Confirm isolation from `mininet>`:

```text
h1 ping -c 2 -W 1 10.0.0.10
h2 ping -c 2 -W 1 10.0.0.10
```

h1 should fail and h2 should still work. Let the UDP command finish before continuing; active high-rate traffic can trigger blocking again after an unblock. Wait about three seconds, then unblock h1 from Terminal 3:

```bash
printf 'UNBLOCK 10.0.0.1\n' | nc 127.0.0.1 8765
```

Confirm h1 recovers with:

```text
h1 ping -c 2 -W 1 10.0.0.10
```

## 8. Demonstrate congestion, response time, and fairness [not yet manually verified]

First ensure h1 is unblocked. At `mininet>`, start two iperf3 servers on the exam server host using different ports:

```text
server iperf3 -s -p 5202 > /tmp/iperf-5202.log 2>&1 &
server iperf3 -s -p 5204 > /tmp/iperf-5204.log 2>&1 &
```

### Baseline measurements (no competing flow)

At `mininet>` run these serially and record the receiver Mbps and average ping RTT:

```text
h1 ping -n -q -i 0.2 -c 10 10.0.0.10
h1 iperf3 -c 10.0.0.10 -p 5202 -t 6
h3 iperf3 -c 10.0.0.10 -p 5202 -t 6
```

h1 crosses the shared inter-switch link; h3 and the server are on the same switch. This compares two paths, not two controller configurations.

### Competing traffic and fairness

Open h1 and h2 xterms from `mininet>`:

```text
xterm h1 h2
```

In the h1 xterm, run:

```bash
iperf3 -c 10.0.0.10 -p 5202 -t 8 -J > /tmp/exam-h1-load.json &
H1_IPERF_PID=$!
ping -n -q -i 0.2 -c 35 10.0.0.10
wait "$H1_IPERF_PID"
```

At nearly the same time, run this in the h2 xterm:

```bash
iperf3 -c 10.0.0.10 -p 5204 -t 8 -J > /tmp/exam-h2-load.json
```

Record h1's average RTT while both transfers run and compare it with the baseline RTT. After both iperf3 commands finish, in either xterm, extract the receiver rates and compute Jain's fairness index:

```bash
python3 -c 'import json; a=json.load(open("/tmp/exam-h1-load.json"))["end"]["sum_received"]["bits_per_second"]/1e6; b=json.load(open("/tmp/exam-h2-load.json"))["end"]["sum_received"]["bits_per_second"]/1e6; print(f"h1={a:.3f} Mbps h2={b:.3f} Mbps Jain={(a+b)**2/(2*(a*a+b*b)):.4f}")'
```

A Jain index of 1 means the two measured rates are equal; values closer to 0 indicate more unequal rates. The shared link is configured at 5 Mbps, so expect the sum to be around that capacity, subject to protocol overhead and emulation variance. Repeat the comparison if asked for stable measurements; the automated experiment runs synchronized trials three times.

## 9. Clean up the manual demo

Close client and iperf xterms. At `mininet>`, exit the topology:

```text
exit
```

Stop the controller in Terminal 1 with Ctrl+C. Do not use broad `killall` commands. If a demo command failed, retain its terminal output and controller status before cleanup so the failure can be diagnosed.

## Feature-to-demo map

| Requirement or behavior | Manual section |
|---|---|
| Environment, topology, source, configuration | 1–2 |
| Concurrent TCP clients and duplicate active IDs | 3 |
| Questions, answer replacement, navigation, submission, score | 3 |
| Quit and server-enforced timer | 3 and 5 |
| TCP protocol and invalid command handling | 4 |
| Application event logging | 3 |
| SDN controller status, validation, manual block/unblock | 2 and 6 |
| Automatic traffic-triggered block and unaffected client | 7 |
| Recovery after policy block | 6–7 |
| Congestion, RTT, throughput, fairness comparison | 8 |
| Automated tests and repeatable network report | 1 (automated-checks note); see [verification playbook](demo-and-verification-playbook.md) |

