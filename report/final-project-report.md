# Online Examination Network — Implementation and Verification Report

**Report date:** 2026-10-25

**Authority:** Official project statement and 40-mark rubric supplied by the student

**Current revision:** Recorded in the Git commit that contains this report.

## Objective

Implement a multi-user TCP examination application and integrate it with an SDN-controlled Mininet network. The project demonstrates threaded client handling, question delivery, answer changes, server-side timing and scoring, application metrics, flow monitoring, a controller-driven traffic-management action, congestion measurements, response-time and throughput-fairness evaluation, and a reproducible demo.

## Design and implementation

The C server accepts clients concurrently and gives each socket its own thread, student ID, answer array, and monotonic deadline. The client and server use newline-framed TCP messages through a shared line reader. The server supports a five-question exam, answer replacement, explicit submission, timeout finalization, scoring, and timestamped CSV outcome metrics.

The Mininet topology has three client hosts and one exam server across two Open vSwitch switches. Host links are configured at 10 Mbps / 2 ms, with a shared 5 Mbps / 5 ms inter-switch link. The OS-Ken controller uses OpenFlow 1.3, learns forwarding state, polls flow counters, exposes a local `STATUS`/`BLOCK`/`UNBLOCK` interface, and can block a source when its measured packet rate reaches the configured threshold.

See `docs/architecture.md` for the message flow, component responsibilities, configuration, ports, and topology.

## Reproduction

On Ubuntu, install the packages listed in the README, create `.venv-sdn`, and install `requirements-sdn.txt`. From any checkout path, run `make test` for application and protocol acceptance tests. Run `make test-controller` for local control-interface checks. With working Open vSwitch and non-interactive sudo access, run `scripts/run_network_validation.sh` for the Mininet policy, connectivity, congestion, automatic-block, recovery, and throughput experiment.

## Verification performed for this revision

| Check | Result | Scope |
|---|---|---|
| C build with project warning flags | PASS | Built client, server, and protocol test executable |
| Protocol tests | PASS | Fragmented lines, CRLF, multiple frames, oversized-frame recovery, deadline |
| Application acceptance tests | PASS, 8 tests | Client flow, all questions, answer change, invalid answer, ten concurrent isolated exams, slow handshake, duplicate ID, timer finalization, CSV metrics |
| Response-time and fairness metric unit tests | PASS, 5 tests | Ping RTT summary parsing and Jain fairness index behavior, including invalid inputs |
| Controller control test | PASS, 1 test | Temporary OS-Ken process; status/configuration, fragmented command, invalid IP, protected server address, block/unblock |
| Python and shell syntax | PASS | Controller, topology, scripts, tests |
| Pinned OS-Ken dependency setup | PASS | Installed `requirements-sdn.txt` into a new temporary Python 3.14 virtual environment; OS-Ken 3.1.1 executable started |
| Checkout-relative scripts | PASS | `scripts/run_all.sh --app-only` invoked from `/tmp` |
| GitHub Actions on Ubuntu 24.04 | PASS | C build/application tests, Python syntax, fresh pinned OS-Ken installation, and controller control test |
| C exam clients/server over Mininet and OpenFlow | PASS in latest validation run | h1 completed with 1/5 and h2 with 0/5 through the C server; two switches connected and SDN policy test passed |
| Socket–SDN policy interaction | PASS in latest validation run | Auto-block denied h1 exam TCP; h2 completed an exam while h1 was blocked; h1 completed an exam after unblock |
| Connectivity, congestion, automatic block and recovery | PASS in latest validation run | 12/12 pings; controlled source block detected; h2 stayed connected; h1 recovered after unblock |
| Response-time and fairness Mininet measurements | PASS on the tested working tree | Three simultaneous h1/h2 throughput trials, Jain index, baseline and loaded h1 ICMP RTT; source hashes are preserved in `results/network_validation_20261025_150625.txt` |

### Recorded network environment and measurements

The latest successful network run was performed on Ubuntu 26.04.1 LTS, kernel 7.0.0-38-generic, Python 3.14.4, GCC 15.2.0, Mininet 2.3.0, Open vSwitch 3.7.1, OS-Ken 3.1.1, and iperf3 3.20. It used 10 Mbps / 2 ms host links and a 5 Mbps / 5 ms inter-switch link. The runner's Git HEAD field predates local uncommitted changes, so the report also includes SHA-256 hashes of the measured topology, metrics helper, validation runner, and unchanged controller source.

| Path and condition | Samples (Mbps) | Mean / result |
|---|---:|---:|
| h1 to server, cross-switch baseline | 4.470, 4.536, 4.474 | 4.493 Mbps |
| h3 to server, same-switch baseline | 9.391, 9.385, 9.387 | 9.388 Mbps |
| Concurrent shared-link trial means | h1 2.256, 2.250, 2.256; h2 2.256, 2.251, 2.256 | h1 2.254 Mbps; h2 2.254 Mbps |
| Jain throughput fairness | 1.0000, 1.0000, 1.0000 | Mean 1.0000 |
| h1 average ICMP RTT | Baseline 19.572 ms; loaded 300.700, 303.859, 302.781 ms | Loaded mean 302.447 ms |

The run reported 0% ping loss, detected and blocked h1 during the controlled UDP burst, denied h1's exam TCP connection while blocked, allowed h2 to complete an exam, and confirmed h1 completed an exam after unblock. The complete summary is `results/network_validation_20261025_150625.txt`. It records Git HEAD `1fd4547005ca436ae9eeef23532d8bdaf1248826` plus SHA-256 fingerprints for the local source files used by the updated experiment. The fairness result describes two TCP flows in this particular Mininet bottleneck; it is not a claim about broader scheduling fairness.

The controller smoke test emitted an Eventlet deprecation warning from OS-Ken's dependency stack. The control test itself passed. The controller uses the pinned OS-Ken release required by the current implementation; replacing its eventlet-based runtime would be an architectural migration outside this implementation phase.

## Historical evidence

The committed October 24 reports predate this implementation and describe the previous source state. In particular, the older automatic-block report did not confirm detection, while an older comparison report made a contrary claim. Those logs are preserved but are not current-revision evidence. Iterative October 25 network runs exposed and fixed iperf3 single-test handling, repeated blocking while the flood remained active, and idempotent cleanup. The successful current-revision report includes the C exam application over Mininet, direct socket–SDN policy interaction, and network performance checks.

## Remaining limitations

The application, controller, metric-unit, and full Mininet checks pass for the source files identified in the latest network report. Performance numbers describe this one emulated topology and should not be generalized to a physical network. Student IDs are not authentication; flow-rate blocking is a lab traffic policy with possible false positives. The prototype is not production exam infrastructure.
