# Online Examination Network — Implementation and Verification Report

**Report date:** 2026-11-02

**Authority:** Official project statement and 40-mark rubric supplied by the student

**Evidence provenance:** The latest two full network runs from a fresh clone are recorded in `results/network_validation_20261102_180207.txt` and `results/network_validation_20261102_175907.txt`.

## Objective

Implement a multi-user TCP examination application and integrate it with an SDN-controlled Mininet network. The project demonstrates threaded client handling, question delivery, answer changes, server-side timing and scoring, application metrics, flow monitoring, a controller-driven traffic-management action, congestion measurements, response-time and throughput-fairness evaluation, and a reproducible demo.

## Design and implementation

The C server accepts clients concurrently and gives each socket its own thread, student ID, answer array, and monotonic deadline. The client and server use newline-framed TCP messages through a shared line reader. The server supports a five-question exam, answer replacement, explicit submission, timeout finalization, scoring, and timestamped CSV outcome metrics.

The Mininet topology has three client hosts and one exam server across two Open vSwitch switches. Host links are configured at 10 Mbps / 2 ms, with a shared 5 Mbps / 5 ms inter-switch link. The OS-Ken controller uses OpenFlow 1.3, learns forwarding state, polls flow counters, exposes a local `STATUS`/`BLOCK`/`UNBLOCK` interface, and can block a source when its measured packet rate reaches the configured threshold.

See `docs/architecture.md` for the message flow, component responsibilities, configuration, ports, and topology.

## Reproduction

On Ubuntu, install the packages listed in the README, create `.venv-sdn`, and install `requirements-sdn.txt`. From any checkout path, run `make test` for application and protocol acceptance tests. Run `make test-controller` for local control-interface checks. With working Open vSwitch and sudo access, run `sudo -v` and then `scripts/run_network_validation.sh` in the same terminal for the Mininet policy, connectivity, congestion, automatic-block, recovery, response-time, and fairness experiment.

## Verification performed for this revision

| Check | Result | Scope |
|---|---|---|
| C build with project warning flags | PASS | Built client, server, and protocol test executable |
| Protocol tests | PASS | Fragmented lines, CRLF, multiple frames, oversized-frame recovery, deadline |
| Application acceptance tests | PASS, 10 tests | Client flow, all questions, answer change, navigation, invalid answer/command, quit, ten concurrent isolated exams, slow handshake, duplicate ID, timer finalization, CSV metrics |
| Response-time and fairness metric unit tests | PASS, 5 tests | Ping RTT summary parsing and Jain fairness index behavior, including invalid inputs |
| Controller control test | PASS, 1 test | Temporary OS-Ken process; status/configuration, fragmented command, invalid IP, protected server address, block/unblock |
| Python and shell syntax | PASS | Controller, topology, scripts, tests |
| Pinned OS-Ken dependency setup | PASS | Installed `requirements-sdn.txt` into a new temporary Python 3.14 virtual environment; OS-Ken 3.1.1 executable started |
| Checkout-relative scripts | PASS | `scripts/run_all.sh --app-only` invoked from `/tmp` |
| GitHub Actions on Ubuntu 24.04 | PASS on commits `eaead4b` and `9dcbec8` | Workflow ran C/application and metric-unit tests, Python syntax, pinned OS-Ken installation, and the controller control test. Mininet remains a separate local validation because it requires a privileged network environment |
| C exam clients/server over Mininet and OpenFlow | PASS in both 2026-11-02 validation runs | h1 completed with 1/5 and h2 with 0/5 through the C server; two switches connected and SDN policy test passed |
| Socket–SDN policy interaction | PASS in both 2026-11-02 validation runs | Auto-block denied h1 exam TCP; h2 completed an exam while h1 was blocked; h1 completed an exam after unblock |
| Connectivity, congestion, automatic block and recovery | PASS in both 2026-11-02 validation runs | 12/12 pings; controlled source block detected; h2 stayed connected; h1 recovered after unblock |
| Response-time and fairness Mininet measurements | PASS in both 2026-11-02 validation runs | Three simultaneous h1/h2 throughput trials, Jain index, baseline and loaded h1 ICMP RTT; report records Git revision `92d56a9` |

### Latest recorded network measurements (2026-11-02)

The latest successful network run used a fresh clone at Git revision `92d56a92f276d389dc16a1952d7d47614eef21a7`. Later commits changed documentation only; the topology, metrics helper, validation runner, and controller are unchanged. The November 2 summaries do not record OS and tool versions, so these measurements should not be attributed to a specific Mininet, Open vSwitch, Python, or iperf3 release. The topology used 10 Mbps / 2 ms host links and a 5 Mbps / 5 ms inter-switch link.

| Path and condition | Samples (Mbps) | Mean / result |
|---|---:|---:|
| h1 to server, cross-switch baseline | 4.472, 4.468, 4.468 | 4.469 Mbps |
| h3 to server, same-switch baseline | 9.406, 9.404, 9.395 | 9.402 Mbps |
| Concurrent shared-link trial means | h1 2.418, 2.257, 2.259; h2 2.259, 2.257, 2.258 | h1 2.312 Mbps; h2 2.258 Mbps |
| Jain throughput fairness | 0.9988, 1.0000, 1.0000 | Mean 0.9996 |
| h1 average ICMP RTT | Baseline 19.441 ms; loaded 302.866, 302.722, 301.479 ms | Loaded mean 302.356 ms |

Both runs reported 0% ping loss, detected and blocked h1 during the controlled UDP burst, denied h1's exam TCP connection while blocked, allowed h2 to complete an exam, and confirmed h1 completed an exam after unblock. The latest complete summary is `results/network_validation_20261102_180207.txt`; the preceding run is `results/network_validation_20261102_175907.txt`. The fairness result describes two TCP flows in this particular Mininet bottleneck; it is not a claim about broader scheduling fairness. The user also confirmed that the manual congestion and fairness demonstration worked; no separate manual measurement values were supplied for this report.

The controller smoke test emitted an Eventlet deprecation warning from OS-Ken's dependency stack. The control test itself passed. The controller uses the pinned OS-Ken release required by the current implementation; replacing its eventlet-based runtime would be an architectural migration outside this implementation phase.

## Historical evidence

The October 24 and earlier October 25 reports predate the latest validated implementation and describe earlier source states. In particular, an older automatic-block report did not confirm detection, while an older comparison report made a contrary claim. Those logs are preserved but are not evidence for the latest source. Iterative October 25 network runs exposed and fixed iperf3 single-test handling, repeated blocking while the flood remained active, and idempotent cleanup. The latest successful report includes the C exam application over Mininet, direct socket–SDN policy interaction, response-time and fairness measurements, and network performance checks.

## Remaining limitations

The application, controller, metric-unit, and full Mininet checks pass for the source files identified in the latest network report. Performance numbers describe this one emulated topology and should not be generalized to a physical network. Student IDs are not authentication; flow-rate blocking is a lab traffic policy with possible false positives. The prototype is not production exam infrastructure.
