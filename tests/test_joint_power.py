from fractions import Fraction as F
import math
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from joint_power import Sample, analyze, read_samples

ROOT = Path(__file__).resolve().parents[1]


def exact_oracle(a, b, c, d, dt):
    """Exact rational coefficient integral; scale by 2*pi/60 afterward."""
    coefficients = [a*c, a*(d-c) + c*(b-a), (b-a)*(d-c)]
    p, q, r = coefficients
    roots = {F(0), F(1)}
    for x, y in [(a, b), (c, d)]:
        if x != y and 0 < (root := F(-x, y-x)) < 1:
            roots.add(root)
    roots = sorted(roots)

    def integral(x):
        return p*x + q*x*x/2 + r*x*x*x/3

    def product(x):
        return p + q*x + r*x*x

    pieces = [(integral(y)-integral(x))*dt for x, y in zip(roots, roots[1:])]
    extremes = [F(0), F(1)]
    if r and 0 < (vertex := F(-q, 2*r)) < 1:
        extremes.append(vertex)
    scale = math.pi / 30
    return (float(sum(max(0, x) for x in pieces)) * scale,
            float(sum(max(0, -x) for x in pieces)) * scale,
            float(max(0, *(product(x) for x in extremes))) * scale,
            float(max(0, *(-product(x) for x in extremes))) * scale)


class PowerTest(unittest.TestCase):
    def run_fixture(self, name):
        return analyze(read_samples(ROOT / "examples" / name))

    def close(self, actual, target):
        self.assertTrue(math.isclose(actual, target, rel_tol=1e-11, abs_tol=1e-11),
                        (actual, target))

    def test_static_torque_does_not_deliver_shaft_power(self):
        a = self.run_fixture("hold.csv")
        self.assertEqual(a["duration_s"], 2)
        self.assertTrue(all(v == 0 for k, v in a.items() if k != "duration_s"))

    def test_quadratic_ramp_has_interior_peak_and_energy(self):
        a = self.run_fixture("coupled-ramp.csv")
        self.close(a["peak_motoring_power_w"], 3*math.pi)
        self.close(a["motoring_energy_j"], 4*math.pi)
        self.assertEqual(a["braking_energy_magnitude_j"], 0)

    def test_same_endpoint_sign_can_hide_braking(self):
        a = self.run_fixture("two-crossings.csv")
        self.close(a["motoring_energy_j"], 16*math.pi/3)
        self.close(a["braking_energy_magnitude_j"], 8*math.pi/3)
        self.close(a["peak_braking_power_magnitude_w"], 2*math.pi)

    def test_multi_interval_duration_mean_and_net(self):
        a = self.run_fixture("stop-and-return.csv")
        self.assertEqual(a["duration_s"], 3)
        self.close(a["motoring_energy_j"], 6*math.pi)
        self.close(a["braking_energy_magnitude_j"], 6*math.pi)
        self.close(a["net_mechanical_energy_j"], 0)
        self.close(a["mean_signed_power_w"], 0)
        self.close(a["peak_motoring_power_w"], 8*math.pi)
        self.close(a["peak_braking_power_magnitude_w"], 8*math.pi)

    def test_random_integer_segments_against_exact_integral(self):
        rng = random.Random(174)
        keys = ("motoring_energy_j", "braking_energy_magnitude_j",
                "peak_motoring_power_w", "peak_braking_power_magnitude_w")
        for _ in range(400):
            a, b, c, d = (rng.randint(-20, 20) for _ in range(4))
            dt = rng.randint(1, 9)
            with self.subTest(a=a, b=b, c=c, d=d, dt=dt):
                result = analyze([Sample(3, a, c), Sample(3+dt, b, d)])
                for k, target in zip(keys, exact_oracle(a, b, c, d, dt)):
                    self.close(result[k], target)

    def test_insert_interpolated_sample_changes_nothing(self):
        a, b = Sample(2, 3, 60), Sample(6, -1, -180)
        actual = analyze([a, Sample(3, 2, 0), b])
        for k, v in analyze([a, b]).items():
            self.close(actual[k], v)

    def test_change_of_joint_coordinate_sign(self):
        trace = [Sample(0, 3, 60), Sample(4, -1, -180)]
        self.assertEqual(analyze(trace), analyze([
            Sample(s.time_s, -s.torque_nm, -s.speed_rpm) for s in trace
        ]))

    def test_invalid_traces(self):
        x = Sample(0, 3, 60)
        for samples in ([x], [x, x], [Sample(-1, 0, 0), x],
                        [x, Sample(1, math.nan, 1)], [x, Sample(1, 0, math.inf)],
                        [x, Sample(1, 0, 1e10)]):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                analyze(samples)

    def test_cli_rejects_bad_header_and_missing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = Path(folder) / "bad.csv"
            bad.write_text("time_s,torque_nm,speed_rad_s\n0,1,2\n", encoding="utf-8")
            for path, fragment in [(bad, "expected header"), (bad.with_name("missing.csv"), "error:")]:
                p = subprocess.run([sys.executable, str(ROOT / "joint_power.py"), str(path)],
                                   capture_output=True, text=True)
                self.assertEqual(p.returncode, 2)
                self.assertIn(fragment, p.stderr)
                self.assertEqual(p.stdout, "")


if __name__ == "__main__":
    unittest.main()
