import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from delivery import RangeError, next_offset, parse_range, serve
from device import (DOWNLOADING, FAILED, IDLE, REBOOTING, SUCCESS, VERIFYING,
                    Device, UpdateError)
from manifest import (ManifestError, Version, build, check, sha256_bytes, sign,
                      verify)
from rollout import Rollout, bucket_of

SECRET = b"test-secret"
FW = bytes(range(256)) * 20          # 5120 字节


class TestVersion(unittest.TestCase):
    def test_ordering(self):
        self.assertLess(Version("1.2.0"), Version("1.10.0"))
        self.assertEqual(Version("v1.0.0"), Version("1.0.0"))
    def test_invalid(self):
        for bad in ("1.0", "abc", "1.0.0-beta"):
            with self.assertRaises(ManifestError):
                Version(bad)


class TestManifest(unittest.TestCase):
    def setUp(self):
        self.m = build("1.2.0", FW, SECRET, min_battery=30)
    def test_sign_verify(self):
        self.assertTrue(verify(self.m, SECRET))
        self.assertFalse(verify(self.m, b"other"))
    def test_tampered_field_detected(self):
        m2 = dict(self.m, size=FW.__len__() - 1)
        self.assertFalse(verify(m2, SECRET))
    def test_missing_signature(self):
        with self.assertRaises(ManifestError):
            verify({"version": "1.0.0"}, SECRET)
    def test_check_ok(self):
        r = check(self.m, FW, SECRET, current_version="1.1.0", battery=80)
        self.assertTrue(r["ok"])
    def test_check_detects_corruption(self):
        r = check(self.m, FW[:-1] + b"\x01", SECRET)
        self.assertFalse(r["ok"])
        self.assertIn("SHA-256 不符", r["problems"])
    def test_check_low_battery(self):
        self.assertIn("电量不足", check(self.m, FW, SECRET, battery=5)["problems"][0])
    def test_check_same_version_skipped(self):
        r = check(self.m, FW, SECRET, current_version="1.2.0")
        self.assertIn("版本不高于当前版本，跳过", r["problems"])
    def test_signature_is_hmac(self):
        s1 = sign({"a": 1}, b"k")["signature"]
        s2 = sign({"a": 1}, b"k")["signature"]
        self.assertEqual(s1, s2)
        self.assertEqual(len(s1), 64)


class TestDelivery(unittest.TestCase):
    def test_full_body_without_range(self):
        r = serve(FW, None, max_chunk=10**6)
        self.assertEqual((r.status, r.start, r.end), (200, 0, len(FW) - 1))
        self.assertEqual(r.body, FW)
    def test_range_with_end(self):
        r = serve(FW, "bytes=100-199")
        self.assertEqual(r.body, FW[100:200])
        self.assertEqual(r.headers["Content-Range"], f"bytes 100-199/{len(FW)}")
        self.assertEqual(r.digest, sha256_bytes(FW[100:200]))
    def test_open_ended_range(self):
        r = serve(FW, "bytes=5000-")
        self.assertEqual(r.end, len(FW) - 1)
        self.assertIsNone(next_offset(r))
    def test_suffix_range(self):
        r = serve(FW, "bytes=-50")
        self.assertEqual(r.body, FW[-50:])
    def test_chunk_cap(self):
        r = serve(FW, "bytes=0-", max_chunk=100)
        self.assertEqual(len(r.body), 100)
        self.assertEqual(r.end, 99)
    def test_bad_ranges(self):
        for bad in ("bytes=50000-", "bytes=9-3", "chars=0-1", "bytes=0-1,5-6"):
            with self.assertRaises(RangeError):
                parse_range(bad, len(FW))
    def test_empty_firmware(self):
        with self.assertRaises(RangeError):
            serve(b"", None)


class TestDevice(unittest.TestCase):
    def setUp(self):
        self.m = build("1.2.0", FW, SECRET)
        self.d = Device("dev-1", version="1.1.0")

    def download(self, chunk=1024):
        self.d.begin(self.m, now=0)
        off = 0
        while off is not None:
            r = serve(FW, f"bytes={off}-", max_chunk=chunk)
            self.d.accept_chunk(r.start, r.body, r.digest, chunk_sha=r.digest)
            off = next_offset(r)

    def test_happy_path(self):
        self.download()
        self.assertEqual(self.d.finish_download(self.m, len(FW)), VERIFYING)
        self.assertEqual(self.d.verify(sha256_bytes(bytes(self.d.buffer)) == self.m["sha256"]),
                         "flashing")
        self.assertEqual(self.d.flash(), REBOOTING)
        self.assertEqual(self.d.boot(True), SUCCESS)
    def test_reject_out_of_order_chunk(self):
        self.d.begin(self.m, 0)
        r = serve(FW, "bytes=0-", max_chunk=100)
        with self.assertRaises(UpdateError):
            self.d.accept_chunk(200, r.body, r.digest)
        self.assertEqual(self.d.expected_offset, 0)
    def test_reject_bad_chunk_digest(self):
        self.d.begin(self.m, 0)
        r = serve(FW, "bytes=0-", max_chunk=100)
        with self.assertRaises(UpdateError):
            self.d.accept_chunk(0, r.body, r.digest, chunk_sha="deadbeef")
        self.assertEqual(self.d.state, FAILED)
    def test_size_mismatch_fails(self):
        self.d.begin(self.m, 0)
        r = serve(FW, "bytes=0-", max_chunk=100)
        self.d.accept_chunk(r.start, r.body, r.digest)
        with self.assertRaises(UpdateError):
            self.d.finish_download(self.m, len(FW))
        self.assertEqual(self.d.state, FAILED)
    def test_state_guards(self):
        with self.assertRaises(UpdateError):
            self.d.finish_download(self.m, len(FW))     # 未 begin
        self.d.begin(self.m, 0)
        with self.assertRaises(UpdateError):
            self.d.verify(True)                        # 还在下载
    def test_verify_fail_then_rollback(self):
        self.download()
        self.d.finish_download(self.m, len(FW))
        self.assertEqual(self.d.verify(False), FAILED)
        r = self.d.rollback("1.1.0")
        self.assertEqual((r["state"], r["version"]), (FAILED, "1.1.0"))
        self.assertEqual(len(self.d.buffer), 0)
    def test_watchdog(self):
        self.d.begin(self.m, 0)
        self.assertFalse(self.d.watchdog(10, 0, timeout=30))
        self.assertTrue(self.d.watchdog(100, 0, timeout=30))
        self.assertEqual(self.d.state, FAILED)
    def test_watchdog_ignores_idle(self):
        self.assertFalse(self.d.watchdog(10**9, 0, timeout=1))


class TestRollout(unittest.TestCase):
    def test_bucket_stable(self):
        self.assertEqual(bucket_of("dev-1"), bucket_of("dev-1"))
        self.assertTrue(0 <= bucket_of("x") < 100)
    def test_first_stage_small_subset(self):
        ro = Rollout()
        ids = [f"d{i}" for i in range(200)]
        hit = sum(1 for d in ids if ro.eligible(d))
        self.assertTrue(0 < hit < 60)
    def test_promote_and_limits(self):
        ro = Rollout()
        self.assertEqual(ro.promote()["stage"], 25)
        self.assertEqual(ro.promote()["stage"], 100)
        self.assertTrue(ro.promote()["done"])
    def test_halt_on_high_failure(self):
        ro = Rollout(failure_threshold=0.2, min_samples=10)
        for i in range(10):
            ro.report(f"d{i}", ok=(i < 7))
        r = ro.report("d10", ok=False)
        self.assertTrue(r["halted"])
        self.assertTrue(ro.rolled_back)
        self.assertEqual(ro.percent, 0)
    def test_no_halt_before_min_samples(self):
        ro = Rollout(failure_threshold=0.2, min_samples=10)
        ro.report("d0", ok=False)
        self.assertFalse(ro.halted)
    def test_promote_after_halt_raises(self):
        ro = Rollout(failure_threshold=0.2, min_samples=5)
        for i in range(5):
            ro.report(f"d{i}", ok=False)
        with self.assertRaises(RuntimeError):
            ro.promote()


if __name__ == "__main__":
    unittest.main()
