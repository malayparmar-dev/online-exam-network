# Online Examination Network — Implementation and Verification Report

**Report date:** 2026-10-25

**Authority:** Official project statement and 40-mark rubric supplied by the student

**Current revision:** Recorded in the Git commit that contains this report.

## Objective

Implement a multi-user TCP examination application and integrate it with an SDN-controlled Mininet network. The project demonstrates threaded client handling, question delivery, answer changes, server-side timing and scoring, application metrics, flow monitoring, a controller-driven traffic-management action, congestion measurements, and a reproducible demo.

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
| Controller control test | PASS, 1 test | Temporary OS-Ken process; status/configuration, fragmented command, invalid IP, protected server address, block/unblock |
| Python and shell syntax | PASS | Controller, topology, scripts, tests |
| Pinned OS-Ken dependency setup | PASS | Installed `requirements-sdn.txt` into a new temporary Python 3.14 virtual environment; OS-Ken 3.1.1 executable started |
| Checkout-relative scripts | PASS | `scripts/run_all.sh --app-only` invoked from `/tmp` |
| GitHub Actions on Ubuntu 24.04 | PASS | C build/application tests, Python syntax, fresh pinned OS-Ken installation, and controller control test |
| C exam clients/server over Mininet and OpenFlow | PASS on `1ed8f9ee87ea741100ff58807fcbf51ce2884c36` | h1 completed with 1/5 and h2 with 0/5 through the C server; two switches connected and SDN policy test passed |
| Socket–SDN policy interaction | PASS on `1ed8f9ee87ea741100ff58807fcbf51ce2884c36` | Auto-block denied h1 exam TCP; h2 completed an exam while h1 was blocked; h1 completed an exam after unblock |
| Connectivity, congestion, automatic block and recovery | PASS on `1ed8f9ee87ea741100ff58807fcbf51ce2884c36` | 12/12 pings; controlled source block detected; h2 stayed connected; h1 recovered after unblock |

### Recorded network environment and measurements

The successful current-revision run was performed on Ubuntu 26.04.1 LTS, kernel 7.0.0-38-generic, Python 3.14.4, GCC 15.2.0, Mininet 2.3.0, Open vSwitch 3.7.1, OS-Ken 3.1.1, and iperf3 3.20. It used 10 Mbps / 2 ms host links and a 5 Mbps / 5 ms inter-switch link.

| Path and condition | Samples (Mbps) | Mean / result |
|---|---:|---:|
| h1 to server, cross-switch baseline | 4.476, 4.468, 4.470 | 4.471 Mbps |
| h3 to server, same-switch baseline | 9.383, 9.082, 9.076 | 9.180 Mbps |
| h1 while h2 loads the shared link | 0.911 | h2 measured 3.942 Mbps concurrently |

The run reported 0% ping loss, detected and blocked h1 during the controlled UDP burst, denied h1's exam TCP connection while blocked, allowed h2 to complete an exam, and confirmed h1 completed an exam after unblock. The complete summary is `results/network_validation_20261025_142820.txt`; it records source revision `1ed8f9ee87ea741100ff58807fcbf51ce2884c36`. These measurements describe only this Mininet configuration.

The controller smoke test emitted an Eventlet deprecation warning from OS-Ken's dependency stack. The control test itself passed. The controller uses the pinned OS-Ken release required by the current implementation; replacing its eventlet-based runtime would be an architectural migration outside this implementation phase.

## Historical evidence

The committed October 24 reports predate this implementation and describe the previous source state. In particular, the older automatic-block report did not confirm detection, while an older comparison report made a contrary claim. Those logs are preserved but are not current-revision evidence. Iterative October 25 network runs exposed and fixed iperf3 single-test handling, repeated blocking while the flood remained active, and idempotent cleanup. The successful current-revision report includes the C exam application over Mininet, direct socket–SDN policy interaction, and network performance checks.

## Remaining limitations

The current source and tests meet the supplied functional rubric, with the Mininet evidence recorded above. Re-run the documented tests after changing the source or the target environment. Performance numbers describe this one emulated topology and should not be generalized to a physical network. Student IDs are not authentication; flow-rate blocking is a lab traffic policy with possible false positives. The prototype is not production exam infrastructure.
