"""Analyze signed mechanical power at one rotary joint from a CSV trace."""
import argparse
import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path

HEADER = ["time_s", "torque_nm", "speed_rpm"]
MAX_MAGNITUDE = 1e9
RPM_TO_RAD_S = math.tau / 60


@dataclass(frozen=True)
class Sample:
    time_s: float
    torque_nm: float
    speed_rpm: float


def read_samples(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        if next(reader, None) != HEADER:
            raise ValueError("expected header: " + ",".join(HEADER))
        samples = []
        for row in reader:
            if len(row) != 3:
                raise ValueError(f"line {reader.line_num}: expected three fields")
            try:
                sample = Sample(*map(float, row))
            except ValueError as exc:
                raise ValueError(f"line {reader.line_num}: expected numeric fields") from exc
            samples.append(sample)
    return samples


def analyze(samples):
    """Assume torque and speed vary linearly between consecutive sample times."""
    if len(samples) < 2:
        raise ValueError("need at least two samples")
    for i, sample in enumerate(samples):
        if any(not math.isfinite(v) or abs(v) > MAX_MAGNITUDE
               for v in (sample.time_s, sample.torque_nm, sample.speed_rpm)):
            raise ValueError(f"sample {i + 1}: use finite values with magnitude at most 1e9")
        if sample.time_s < 0 or (i and sample.time_s <= samples[i - 1].time_s):
            raise ValueError(f"sample {i + 1}: time must be nonnegative and strictly increasing")

    positive_parts, braking_parts = [], []
    peak, minimum = -math.inf, math.inf
    for left, right in zip(samples, samples[1:]):
        dt = right.time_s - left.time_s
        a, b = left.torque_nm, right.torque_nm
        c, d = left.speed_rpm, right.speed_rpm

        def power(u):
            return ((1 - u) * a + u * b) * ((1 - u) * c + u * d) * RPM_TO_RAD_S

        cuts = {0.0, 1.0}
        for start, end in ((a, b), (c, d)):
            if (start < 0 < end) or (end < 0 < start):
                cuts.add(start / (start - end))
        knots = sorted(cuts)
        for x, y in zip(knots, knots[1:]):
            mid = (x + y) / 2
            # Simpson integration is exact for the modeled quadratic on each piece.
            energy = (power(x) + 4 * power(mid) + power(y)) * ((y - x) * dt / 6)
            if energy > 0:
                positive_parts.append(energy)
            elif energy < 0:
                braking_parts.append(-energy)

        candidates = [power(0), power(1)]
        curvature = (b - a) * (d - c)
        if curvature:
            vertex = -(a * (d - c) + c * (b - a)) / (2 * curvature)
            if 0 < vertex < 1:
                candidates.append(power(vertex))
        peak = max(peak, *candidates)
        minimum = min(minimum, *candidates)

    supplied, braking = math.fsum(positive_parts), math.fsum(braking_parts)
    duration = samples[-1].time_s - samples[0].time_s
    net = supplied - braking
    return {
        "duration_s": duration,
        "motoring_energy_j": supplied,
        "braking_energy_magnitude_j": braking,
        "net_mechanical_energy_j": net,
        "mean_signed_power_w": net / duration,
        "peak_motoring_power_w": max(0.0, peak),
        "peak_braking_power_magnitude_w": max(0.0, -minimum),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", help="CSV with time_s,torque_nm,speed_rpm")
    args = parser.parse_args()
    try:
        result = analyze(read_samples(args.csv_file))
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps({k: float(f"{v:.9g}") for k, v in result.items()}, indent=2,
                     allow_nan=False))


if __name__ == "__main__":
    main()
