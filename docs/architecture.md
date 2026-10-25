# System Architecture

## Purpose and scope

The project demonstrates a multi-user TCP examination application integrated with an SDN-controlled Mininet network. The C server is authoritative for session answers, timing, scoring, and results. The SDN controller manages network forwarding, observes OpenFlow counters, and applies source-IP blocking rules when a configured rate threshold is exceeded.

## Application protocol

Messages are UTF-8 text lines terminated by `\n`; a TCP read is not treated as a message boundary. `src/protocol.c` buffers partial input, supports multiple lines received together, strips carriage returns, enforces the message size, and uses monotonic deadlines.

```text
Client -> Server: STUDENT <id>\n
Server -> Client: WELCOME...\n
Server -> Client: Enter START...\n
Client -> Server: START\n
Server -> Client: STARTED: Duration is <seconds> seconds.\n
Client -> Server: GET <1-5>\n
Server -> Client: QUESTION ...\n
Client -> Server: ANSWER <1-5> <A-D>\n
Server -> Client: OK: Answer recorded.\n
Client -> Server: SUBMIT\n
Server -> Client: RESULT: Student=... Score=... Answered=...\n
```

`QUIT` abandons an attempt. At the deadline, the server automatically finalizes and scores the answers, sends a `TIMEOUT` line containing the result, and closes the connection. The default duration is 300 seconds; `EXAM_DURATION_SECONDS` supports short timer tests. IDs are 1–32 ASCII letters, digits, `_`, or `-`, and may be active only once at a time.

## Concurrent sessions and application metrics

The accept loop hands each socket to a detached POSIX thread before reading the student's identity. A slow client therefore does not block acceptance of other clients. Active IDs are protected by a mutex. Each thread owns its question answers and monotonic deadline.

The server writes UTC CSV events to `results/app_metrics.csv` by default. Events include connection, start, question delivery, accepted answers, invalid requests, submission or timer finalization, and disconnect. The CSV includes student ID, timestamp, server-side request processing latency where available, and outcome detail. `EXAM_METRICS_FILE` can select another output path.

## Mininet topology

`src/topology.py` creates two Open vSwitch switches and four hosts:

| Host | Address | Switch |
|---|---|---|
| h1 | 10.0.0.1/24 | s1 |
| h2 | 10.0.0.2/24 | s1 |
| h3 | 10.0.0.3/24 | s2 |
| server | 10.0.0.10/24 | s2 |

Host-facing links are configured for 10 Mbps and 2 ms delay. The shared s1–s2 link is configured for 5 Mbps and 5 ms delay. Thus h1/h2 reach the server across the bottleneck, while h3 is attached to the server's switch.

## SDN controller

`sdn/exam_controller.py` is an OS-Ken OpenFlow 1.3 application. It installs a table-miss rule, learns MAC-to-port locations, installs forwarding rules, and polls flow counters every 2 seconds. The local control socket on `127.0.0.1:8765` supports `STATUS`, `BLOCK <IPv4>`, and `UNBLOCK <IPv4>`. The controller refuses a manual block of the exam server address.

For IPv4 forwarding flows, packet rates are derived from OpenFlow counter deltas over monotonic elapsed time. A source flow at or above the default 5,000 packets/second threshold is blocked on connected switches. The exam server is excluded. `EXAM_AUTO_BLOCK_PPS` and `EXAM_STATS_INTERVAL` are controller environment settings; choose values based on measured benign and test traffic. Blocking applies to all IPv4 traffic from that source IP in this lab, not only exam traffic.

## Ports and configuration

| Setting | Default | Override |
|---|---:|---|
| Exam server TCP port | 8080 | `EXAM_PORT` |
| Exam duration | 300 seconds | `EXAM_DURATION_SECONDS` |
| Metrics CSV path | `results/app_metrics.csv` | `EXAM_METRICS_FILE` |
| OpenFlow listener | 6653 | `EXAM_OPENFLOW_PORT` |
| Controller control interface | 8765 | `EXAM_CONTROL_PORT` |
| Flow statistics interval | 2 seconds | `EXAM_STATS_INTERVAL` |
| Auto-block threshold | 5,000 packets/s | `EXAM_AUTO_BLOCK_PPS` |

The topology and network runner use the default OpenFlow/control ports unless their process environments are configured consistently.
