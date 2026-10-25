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
| Mininet/OpenFlow policy and connectivity | PASS on `c7c8ba3b5d3da77c5afca9b9836f517a2c832948` | Two switches connected, SDN policy test passed, 12/12 pings succeeded |
| Congestion, automatic block, unaffected client and recovery | PASS on `c7c8ba3b5d3da77c5afca9b9836f517a2c832948` | See the saved network report and performance measurements below |
| C exam clients and server over Mininet | PENDING on current revision | Added to the batch test after the saved run; rerun `scripts/run_network_validation.sh` to verify this end-to-end rubric item |

### Recorded network environment and measurements

The successful run was performed on Ubuntu 26.04.1 LTS, kernel 7.0.0-38-generic, Python 3.14.4, GCC 15.2.0, Mininet 2.3.0, Open vSwitch 3.7.1, OS-Ken 3.1.1, and iperf3 3.20. It used 10 Mbps / 2 ms host links and a 5 Mbps / 5 ms inter-switch link.

| Path and condition | Samples (Mbps) | Mean / result |
|---|---:|---:|
| h1 to server, cross-switch baseline | 4.479, 4.469, 4.470 | 4.473 Mbps |
| h3 to server, same-switch baseline | 9.395, 9.389, 9.395 | 9.393 Mbps |
| h1 while h2 loads the shared link | 0.907 | h2 measured 3.940 Mbps concurrently |

The run reported 0% ping loss, detected and blocked h1 during the controlled UDP burst, kept h2 connected, and confirmed h1 recovered after unblock. The complete summary is `results/network_validation_20261025_135431.txt`; it records source revision `c7c8ba3b5d3da77c5afca9b9836f517a2c832948`. These measurements describe only this Mininet configuration.

The controller smoke test emitted an Eventlet deprecation warning from OS-Ken's dependency stack. The control test itself passed. The controller uses the pinned OS-Ken release required by the current implementation; replacing its eventlet-based runtime would be an architectural migration outside this implementation phase.

## Historical evidence

The committed October 24 reports predate this implementation and describe the previous source state. In particular, the older automatic-block report did not confirm detection, while an older comparison report made a contrary claim. Those logs are preserved but are not current-revision evidence. An initial October 25 run on revision `4afd9d9f` exposed that iperf3's server accepts only one test at a time; the congestion test was corrected to use a second server port. The saved successful performance report is from revision `c7c8ba3b`; the current revision adds a further end-to-end exam-over-Mininet check that still needs to pass.

## Remaining verification

Run `scripts/run_network_validation.sh` on the current revision to verify the real C exam client/server over Mininet alongside the already-passing SDN and performance checks. The runner needs interactive sudo authentication; run `sudo -v` first in the same terminal. Add the current-revision report here if the run passes. If the end-to-end scenario fails, fix and rerun it before claiming socket–SDN integration is fully verified.

Performance values from Mininet describe only the specified emulated links. Student IDs are not authentication; flow-rate blocking is a lab traffic policy with possible false positives. The prototype is for coursework demonstration and is not production exam infrastructure.
