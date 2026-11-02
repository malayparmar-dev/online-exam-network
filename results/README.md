# Results and experiment evidence

## Latest successful full network run

Use [`network_validation_20261102_180207.txt`](network_validation_20261102_180207.txt) as the latest successful end-to-end result. It reports the C exam clients over Mininet, controller connectivity and policy, automatic blocking and recovery, throughput, baseline and loaded RTT, and Jain fairness across three concurrent-flow trials. A second full successful run from the same fresh clone is [`network_validation_20261102_175907.txt`](network_validation_20261102_175907.txt). Both reports identify the checkout revision and end with `NETWORK VALIDATION PASSED`.

The summary is tracked in Git. The corresponding `_raw.log` file is generated locally and ignored by Git. Run `./scripts/run_network_validation.sh` to produce a fresh summary and raw log.

## Earlier and historical results

All other files in this directory record earlier partial tests, intermediate network experiments, or runs from older source revisions. Keep them for historical context; do not use them as the latest verification of the current implementation.

In particular, `latest_full_run_report.txt` and `latest_validation_report.txt` are preserved historical pointer files. Their names do not indicate the current authoritative run; use the dated network-validation report above instead.

Some earlier reports contain failed or incomplete experiments. Read each report's own pass, fail, and skip status before citing it. Do not combine measurements from different runs as if they were one experiment. The November 2 results came from a fresh clone at commit `92d56a92f276d389dc16a1952d7d47614eef21a7`; later changes to that commit were documentation-only.
