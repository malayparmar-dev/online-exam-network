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
| Mininet/OpenFlow/congestion/automatic-block experiment | NOT RUN | This account's sudo requires interactive authentication; OVS state could not be inspected as the unprivileged user. No network performance claim is made for this revision. |

The controller smoke test emitted an Eventlet deprecation warning from OS-Ken's dependency stack. The control test itself passed. The controller uses the pinned OS-Ken release required by the current implementation; replacing its eventlet-based runtime would be an architectural migration outside this implementation phase.

## Historical evidence

The committed October 24 reports predate this implementation and describe the previous source state. In particular, the older automatic-block report did not confirm detection, while an older comparison report made a contrary claim. Those logs are preserved but are not current-revision evidence. The new network runner must produce `BATCH TESTS PASSED` and a `PERFORMANCE_JSON` record before network rubric items are reported as verified.

## Remaining work before calling every rubric item verified

1. Run `scripts/run_network_validation.sh` on a host where Mininet and Open vSwitch are available and sudo authentication is configured for the invoking user.
2. Review the generated report for switch connection, ping results, all throughput samples, congestion results, automatic block, unaffected-client connectivity, and recovery.
3. Record the network result, environment versions, Git revision, and measured values here and in the final demo materials. If the automatic block or congestion comparison fails, fix and rerun that specific scenario before claiming it works.

Performance values from Mininet describe only the specified emulated links. Student IDs are not authentication; flow-rate blocking is a lab traffic policy with possible false positives. The prototype is for coursework demonstration and is not production exam infrastructure.
