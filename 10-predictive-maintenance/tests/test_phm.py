import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from features import (band_ratio, bearing_frequencies, crest_factor, extract,
                      harmonics, health_index, kurtosis, rms, spectral_centroid)
from fft import FFTError, band_energy, fft, hann, ifft, peak, spectrum, synthetic
from phm import Monitor
from rul import Trend, alert

FS, N = 2000.0, 2048
FAULTS = bearing_frequencies(1800, 9, 7.94, 39.04)


class TestFFT(unittest.TestCase):
    def test_impulse_flat(self):
        self.assertEqual([round(c.real, 6) for c in fft([1, 0, 0, 0])], [1, 1, 1, 1])
    def test_length_must_be_power_of_two(self):
        for bad in (3, 6, 0):
            with self.assertRaises(FFTError):
                fft([1] * bad)
    def test_roundtrip(self):
        x = [3.0, -1.0, 2.5, 0.5, 1.0, 0.0, -2.0, 4.0]
        back = ifft(fft(x))
        self.assertAlmostEqual(back[0].real, 3.0, places=9)
        self.assertAlmostEqual(back[5].real, 0.0, places=9)
    def test_hann_endpoints(self):
        w = hann(8)
        self.assertEqual((w[0], w[-1]), (0.0, 0.0))
        self.assertAlmostEqual(sum(w), (8 - 1) / 2, places=6)   # 窗增益 = (N-1)/2
    def test_dc_only(self):
        f, a = spectrum([5.0] * N, FS)
        self.assertAlmostEqual(a[0], 5.0, places=6)
    def test_sine_peak(self):
        f, a = spectrum(synthetic(FS, N, [(50.0, 1.0)]), FS)
        pf, pa = peak(f, a)
        self.assertLessEqual(abs(pf - 50.0), FS / N)
        self.assertAlmostEqual(pa, 1.0, delta=0.06)
    def test_band_energy(self):
        f, a = spectrum(synthetic(FS, N, [(50.0, 1.0), (300.0, 0.5)]), FS)
        e_low = band_energy(f, a, 40, 60)
        e_high = band_energy(f, a, 290, 310)
        self.assertGreater(e_low, e_high)


class TestFeatures(unittest.TestCase):
    def test_rms_of_unit_sine(self):
        sig = synthetic(FS, N, [(100.0, 1.0)])
        self.assertAlmostEqual(rms(sig), 0.7071, delta=0.01)
    def test_kurtosis_of_sine(self):
        sig = synthetic(FS, N, [(100.0, 1.0)])
        self.assertAlmostEqual(kurtosis(sig), -1.5, delta=0.05)
    def test_crest_of_sine(self):
        sig = synthetic(FS, N, [(100.0, 1.0)])
        self.assertAlmostEqual(crest_factor(sig), math.sqrt(2), delta=0.02)
    def test_flat_signal(self):
        self.assertEqual((rms([0, 0]), kurtosis([0, 0, 0, 0]), crest_factor([0, 0])),
                         (0.0, 0.0, 0.0))
    def test_centroid_tracks_energy(self):
        f, a = spectrum(synthetic(FS, N, [(100.0, 1.0)]), FS)
        self.assertAlmostEqual(spectral_centroid(f, a), 100.0, delta=1.5)
    def test_bearing_freq_order(self):
        self.assertLess(FAULTS["bpfo"], FAULTS["bpfi"])
        self.assertAlmostEqual(FAULTS["bpfo"], 107.5, delta=0.1)
        self.assertAlmostEqual(FAULTS["bpfi"], 162.5, delta=0.1)
        self.assertEqual(FAULTS["fr"], 30.0)
    def test_harmonics(self):
        self.assertEqual(harmonics(10.0, 3), [10.0, 20.0, 30.0])

    def test_diagnosis_healthy(self):
        e = extract(synthetic(FS, N, [(30.0, 1.0)], noise=0.03), FS, FAULTS)
        self.assertEqual(e["diagnosis"], "healthy")
        self.assertGreater(health_index(e), 90)
    def test_diagnosis_outer_race(self):
        sig = synthetic(FS, N, [(30.0, 0.4), (FAULTS["bpfo"], 0.8),
                                (2 * FAULTS["bpfo"], 0.6), (3 * FAULTS["bpfo"], 0.4)],
                        noise=0.03)
        e = extract(sig, FS, FAULTS)
        self.assertEqual(e["diagnosis"], "outer_race")
        self.assertGreater(e["bpfo_ratio"], 0.5)
        self.assertLess(health_index(e), 60)
    def test_diagnosis_inner_race(self):
        sig = synthetic(FS, N, [(30.0, 0.4), (FAULTS["bpfi"], 0.9),
                                (2 * FAULTS["bpfi"], 0.7)], noise=0.03)
        e = extract(sig, FS, FAULTS)
        self.assertEqual(e["diagnosis"], "inner_race")
    def test_band_ratio_normalised(self):
        f, a = spectrum(synthetic(FS, N, [(30.0, 1.0)]), FS)
        self.assertAlmostEqual(band_ratio(f, a, [30.0], width=8), 1.0, delta=0.05)


class TestRUL(unittest.TestCase):
    def test_exact_linear_slope(self):
        t = Trend(list(range(11)), [10 - 0.5 * i for i in range(11)])
        self.assertAlmostEqual(t.slope, -0.5, places=6)
        self.assertAlmostEqual(t.residual_std, 0.0, places=6)
    def test_rul_value(self):
        t = Trend(list(range(11)), [10 - 0.5 * i for i in range(11)])
        self.assertAlmostEqual(t.rul(10, 2.0), 6.0, places=6)
    def test_improving_trend_no_rul(self):
        t = Trend(list(range(6)), [float(i) for i in range(6)])
        self.assertIsNone(t.rul(5, 100.0))
    def test_already_below_threshold(self):
        t = Trend(list(range(6)), [10 - i for i in range(6)])
        self.assertEqual(t.rul(5, 10.0), 0.0)
    def test_lower_bound_is_pessimistic(self):
        t = Trend(list(range(11)), [10 - 0.5 * i + (0.1 if i % 2 else 0) for i in range(11)])
        self.assertLess(t.rul_lower(10, 2.0), t.rul(10, 2.0))
    def test_too_few_points(self):
        with self.assertRaises(ValueError):
            Trend([0, 1], [1, 2])
    def test_alert_levels(self):
        self.assertEqual(alert(None, 24), "stable")
        self.assertEqual(alert(0.0, 24), "failed")
        self.assertEqual(alert(10, 24), "maintenance_due")
        self.assertEqual(alert(100, 24), "watch")


class TestMonitor(unittest.TestCase):
    def test_empty_report(self):
        self.assertEqual(Monitor(FS, 1800).report()["status"], "no-data")
    def test_degrades_and_alerts(self):
        mon = Monitor(FS, 1800, threshold=45.0, window=48.0)
        for i in range(8):
            amp = 0.15 + 0.11 * i
            block = synthetic(FS, N, [(30.0, 0.5), (FAULTS["bpfo"], amp),
                                      (2 * FAULTS["bpfo"], amp * 0.7)],
                              noise=0.05, seed=i)
            mon.feed(block, t=i * 24.0)
        rep = mon.report()
        self.assertLess(rep["health_now"], rep["health_first"])
        self.assertEqual(rep["diagnosis"], "outer_race")
        self.assertLess(rep["slope"], 0)
        self.assertIsNotNone(rep["rul"])
        self.assertIn(rep["alert"], ("maintenance_due", "watch", "failed"))
    def test_stable_healthy_report(self):
        mon = Monitor(FS, 1800, threshold=40.0)
        for i in range(5):
            mon.feed(synthetic(FS, N, [(30.0, 1.0)], noise=0.03, seed=i), t=i * 24.0)
        rep = mon.report()
        self.assertEqual(rep["diagnosis"], "healthy")
        self.assertEqual(rep["alert"], "stable")


if __name__ == "__main__":
    unittest.main()
