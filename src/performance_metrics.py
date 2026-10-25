"""Small, dependency-free parsers and metrics for the Mininet experiment."""

import re


def average_ping_ms(output, label):
    """Return the average RTT from standard iputils ping summary output."""
    match = re.search(
        r"(?:rtt|round-trip) min/avg/max/(?:mdev|stddev) = "
        r"[\d.]+/([\d.]+)/[\d.]+/[\d.]+ ms",
        output,
    )
    if match is None:
        raise RuntimeError(
            f"Could not parse {label} ping RTT output: {output[-500:]}"
        )
    return float(match.group(1))


def jain_fairness_index(throughputs):
    """Calculate Jain's index for contemporaneous non-negative rates."""
    if not throughputs or any(value < 0 for value in throughputs):
        raise ValueError("Fairness requires non-negative throughput samples")
    total = sum(throughputs)
    squares = sum(value * value for value in throughputs)
    if total <= 0 or squares <= 0:
        raise ValueError("Fairness is undefined when all throughput is zero")
    return (total * total) / (len(throughputs) * squares)
