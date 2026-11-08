# -*- coding: utf-8 -*-
"""License v1 / update / integrity tests. Uses throw-away keys; no real keys are needed."""
import base64
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(os.path.abspath(__file__)).parent.parent
sys.path.insert(0, str(ROOT))

import video_studio_integrity as integ  # noqa: E402
from video_studio_license import (  # noqa: E402
    FREE_OPERATIONS,
    PRODUCT_CODE,
    LicenseManager,
    _b64u_encode,
    canonical_json,
    verify_manual_serial,
    verify_signed_payment_info,
    verify_signed_release,
    verify_signed_revoked_list,
    verify_signed_revoked_list_or_none,
)
from video_studio_update import is_newer_version, load_cached_update, parse_version, refresh_update_data, save_cached_update  # noqa: E402


def keypair():
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return priv, base64.b64encode(pub).decode()


def sign(priv, domain, msg: bytes) -> str:
    return _b64u_encode(priv.sign(f"{PRODUCT_CODE}-{domain}|".encode() + msg))


def make_serial(priv, **over):
    now = int(time.time())
    p = {"v": 1, "p": PRODUCT_CODE, "m": "*", "iat": now, "nbf": now - 10, "e": None, "cid": "c1", "name": "Ali", "jti": "abc123def456abcd"}
    p.update(over)
    body = canonical_json(p)
    return f"{PRODUCT_CODE}1-{_b64u_encode(body)}.{sign(priv, 'LIC1', body)}", p


class TestSerial(unittest.TestCase):
    def setUp(self):
        self.priv, self.pub = keypair()

    def test_valid_serial(self):
        s, _ = make_serial(self.priv)
        self.assertEqual(verify_manual_serial(s, "ANY", [], self.pub)[0], "ok")

    def test_tampered_payload_rejected(self):
        s, _ = make_serial(self.priv)
        head, sig = s.split(".")
        bad = head[:-2] + ("AA" if not head.endswith("AA") else "BB") + "." + sig
        self.assertEqual(verify_manual_serial(bad, "ANY", [], self.pub)[0], "invalid")

    def test_wrong_key_rejected(self):
        s, _ = make_serial(self.priv)
        _, other = keypair()
        self.assertEqual(verify_manual_serial(s, "ANY", [], other)[0], "invalid")

    def test_domain_separation(self):
        """A signature made for another purpose must not validate as a serial."""
        now = int(time.time())
        p = {"v": 1, "p": PRODUCT_CODE, "m": "*", "iat": now, "nbf": now, "e": None, "cid": "x", "name": "x", "jti": "j"}
        body = canonical_json(p)
        s = f"{PRODUCT_CODE}1-{_b64u_encode(body)}.{sign(self.priv, 'REVOKED1', body)}"
        self.assertEqual(verify_manual_serial(s, "ANY", [], self.pub)[0], "invalid")

    def test_other_product(self):
        s, _ = make_serial(self.priv, p="XYZ")
        self.assertEqual(verify_manual_serial(s, "ANY", [], self.pub)[0], "product")

    def test_device_binding(self):
        s, _ = make_serial(self.priv, m="DEVICE-A")
        self.assertEqual(verify_manual_serial(s, "DEVICE-B", [], self.pub)[0], "device")
        self.assertEqual(verify_manual_serial(s, "device-a", [], self.pub)[0], "ok")

    def test_expiry_and_not_before(self):
        now = int(time.time())
        s, _ = make_serial(self.priv, nbf=now - 1000, e=now - 10)
        self.assertEqual(verify_manual_serial(s, "A", [], self.pub)[0], "expired")
        s, _ = make_serial(self.priv, nbf=now + 5000)
        self.assertEqual(verify_manual_serial(s, "A", [], self.pub)[0], "not_yet_valid")

    def test_revoked_by_jti(self):
        s, p = make_serial(self.priv)
        self.assertEqual(verify_manual_serial(s, "A", [p["jti"]], self.pub)[0], "disabled")

    def test_garbage(self):
        for g in ("", "abc", "VSP1-.", "VSP1-a.b", "x" * 5000, "VSP1-%%%.%%%"):
            self.assertEqual(verify_manual_serial(g, "A", [], self.pub)[0], "invalid", g[:20])

    def test_no_public_key_configured(self):
        s, _ = make_serial(self.priv)
        self.assertEqual(verify_manual_serial(s, "A", [], "")[0], "invalid")

    def test_nan_rejected(self):
        body = b'{"v":1,"p":"VSP","m":"*","iat":NaN,"nbf":0,"e":null,"cid":"a","name":"a","jti":"j"}'
        s = f"VSP1-{_b64u_encode(body)}.{sign(self.priv, 'LIC1', body)}"
        self.assertEqual(verify_manual_serial(s, "A", [], self.pub)[0], "invalid")


class TestSignedDocs(unittest.TestCase):
    def setUp(self):
        self.rp, self.rpub = keypair()
        self.pp, self.ppub = keypair()
        self.up, self.upub = keypair()

    def doc(self, revoked=("a",), version="9.9.9", url="https://example.com/x.exe", sha=""):
        rel = {"version": version, "url": url, "sha256": sha, "notes": "n"}
        pay = {"price": "10$"}
        return {
            **rel, "update_sig": sign(self.up, "UPDATE1", canonical_json(rel)),
            "revoked": list(revoked), "revoked_sig": sign(self.rp, "REVOKED1", canonical_json(list(revoked))),
            "payment": pay, "payment_sig": sign(self.pp, "PAYMENT1", canonical_json(pay)),
        }

    def test_revoked(self):
        self.assertEqual(verify_signed_revoked_list(self.doc(), self.rpub), ["a"])
        d = self.doc()
        d["revoked"].append("evil")
        self.assertIsNone(verify_signed_revoked_list_or_none(d, self.rpub))

    def test_empty_signed_list_is_valid(self):
        self.assertEqual(verify_signed_revoked_list_or_none(self.doc(revoked=()), self.rpub), [])

    def test_payment(self):
        self.assertEqual(verify_signed_payment_info(self.doc(), self.ppub), {"price": "10$"})
        d = self.doc()
        d["payment"]["price"] = "0$"
        self.assertIsNone(verify_signed_payment_info(d, self.ppub))

    def test_release_ok_and_tamper(self):
        self.assertEqual(verify_signed_release(self.doc(), self.upub)["version"], "9.9.9")
        d = self.doc()
        d["url"] = "https://evil.example/x.exe"
        self.assertIsNone(verify_signed_release(d, self.upub))

    def test_release_requires_https_and_valid_sha(self):
        self.assertIsNone(verify_signed_release(self.doc(url="http://example.com/a"), self.upub))
        self.assertIsNone(verify_signed_release(self.doc(sha="zz"), self.upub))
        self.assertIsNotNone(verify_signed_release(self.doc(sha="a" * 64), self.upub))

    def test_keys_are_not_interchangeable(self):
        self.assertIsNone(verify_signed_release(self.doc(), self.rpub))

    def test_version_compare(self):
        self.assertTrue(is_newer_version("1.10.0", "1.9.9"))
        self.assertFalse(is_newer_version("1.0.0", "1.0.0"))
        self.assertFalse(is_newer_version("0.9", "1.0.0"))  # downgrade guard
        self.assertEqual(parse_version("v2.1"), (2, 1))

    def test_cache_only_valid_signed(self):
        with tempfile.TemporaryDirectory() as d:
            mgr = LicenseManager(Path(d), keys={"serial": self.upub, "revoke": self.rpub, "payment": self.ppub, "update": self.upub})
            save_cached_update(Path(d), self.doc())
            self.assertIsNotNone(load_cached_update(Path(d)))
            import video_studio_update as vu
            orig = vu.fetch_update_json
            try:
                vu.fetch_update_json = lambda *a, **k: {"version": "99", "url": "https://x.y/z", "notes": "", "sha256": ""}  # unsigned
                data, fresh = refresh_update_data("https://x", Path(d), mgr)
                self.assertFalse(fresh)  # unsigned fresh data is ignored; the good cache is used
                self.assertEqual(data["version"], "9.9.9")
            finally:
                vu.fetch_update_json = orig


class TestLicenseManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.priv, self.pub = keypair()

    def tearDown(self):
        self.tmp.cleanup()

    def mgr(self):
        return LicenseManager(self.dir, pub_key_b64=self.pub)

    def test_trial_counts_only_on_consume(self):
        m = self.mgr()
        self.assertEqual(m.remaining_free_operations(), FREE_OPERATIONS)
        for _ in range(FREE_OPERATIONS):
            self.assertTrue(m.consume_operation())
        self.assertFalse(m.can_perform_paid_operation())
        self.assertFalse(m.consume_operation())

    def test_activation_persists(self):
        m = self.mgr()
        s, _ = make_serial(self.priv)
        self.assertEqual(m.activate_key(s), "ok")
        self.assertTrue(self.mgr().is_activated())

    def test_bad_key_not_activated(self):
        m = self.mgr()
        self.assertEqual(m.activate_key("VSP1-abc.def"), "invalid")
        self.assertFalse(m.is_activated())

    def test_state_tamper_penalty(self):
        m = self.mgr()
        m.consume_operation()
        for p in (m.path_a, m.path_b):
            p.write_text(p.read_text().replace('"used_operations": 1', '"used_operations": 0'))
        m2 = self.mgr()
        self.assertEqual(m2.remaining_free_operations(), 0)

    def test_one_copy_deleted_is_restored(self):
        m = self.mgr()
        m.consume_operation()
        m.path_a.unlink()
        self.assertEqual(self.mgr().remaining_free_operations(), FREE_OPERATIONS - 1)

    def test_revocation_applies_only_when_signed(self):
        rp, rpub = keypair()
        m = LicenseManager(self.dir, keys={"serial": self.pub, "revoke": rpub, "payment": rpub, "update": rpub})
        s, p = make_serial(self.priv)
        self.assertEqual(m.activate_key(s), "ok")
        m.apply_update_json({"revoked": [p["jti"]], "revoked_sig": "AAAA"})
        self.assertTrue(m.is_activated())  # forged list ignored
        m.apply_update_json({"revoked": [p["jti"]], "revoked_sig": sign(rp, "REVOKED1", canonical_json([p["jti"]]))})
        self.assertFalse(m.is_activated())

    def test_clock_rollback(self):
        m = self.mgr()
        now = int(time.time())
        m.state["last_seen_ts"] = now + 10 * 86400
        self.assertGreaterEqual(m.effective_now(), now + 10 * 86400)


class TestIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.priv, self.pub = keypair()
        (self.dir / "app.exe").write_bytes(b"binary-data")
        files = {"app.exe": {"sha256": integ.sha256_file(self.dir / "app.exe"), "size": 11}}
        signed = {"version": "1.0.0", "files": files}
        doc = {**signed, "sig": sign(self.priv, "MANIFEST1", canonical_json(signed))}
        (self.dir / "integrity.json").write_text(json.dumps(doc), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_ok(self):
        self.assertEqual(integ.check_integrity(self.dir, self.pub)[0], "ok")

    def test_modified(self):
        (self.dir / "app.exe").write_bytes(b"binary-DATA")
        self.assertEqual(integ.check_integrity(self.dir, self.pub)[0], "mismatch")

    def test_missing_file(self):
        (self.dir / "app.exe").unlink()
        self.assertEqual(integ.check_integrity(self.dir, self.pub)[0], "mismatch")

    def test_forged_manifest(self):
        doc = json.loads((self.dir / "integrity.json").read_text())
        doc["files"]["app.exe"]["sha256"] = "0" * 64
        (self.dir / "integrity.json").write_text(json.dumps(doc))
        self.assertEqual(integ.check_integrity(self.dir, self.pub)[0], "bad_signature")

    def test_no_manifest_is_not_blocking(self):
        (self.dir / "integrity.json").unlink()
        self.assertEqual(integ.check_integrity(self.dir, self.pub)[0], "no_manifest")

    def test_path_traversal(self):
        signed = {"version": "1", "files": {"../x": {"sha256": "0" * 64, "size": 1}}}
        doc = {**signed, "sig": sign(self.priv, "MANIFEST1", canonical_json(signed))}
        (self.dir / "integrity.json").write_text(json.dumps(doc))
        self.assertEqual(integ.check_integrity(self.dir, self.pub)[0], "mismatch")


if __name__ == "__main__":
    unittest.main()
