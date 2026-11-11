# -*- coding: utf-8 -*-
"""
HMZ Video Studio Pro — Licensing engine (Gumroad + offline-verifiable signed serials).

Honest security note: any licensing implemented in Python can be bypassed by a skilled
reverse engineer with enough time. The goal of this design (Ed25519 signatures, domain-separated
messages, dual HMAC-protected state, signed revocation/payment/update data) is to raise the cost of
tampering and to prevent casual key forgery - NOT to be unbreakable. Secrets embedded in a client
(the HMAC key) can be extracted; they only detect casual edits.

Device limits: Gumroad's `uses` counter is an activation counter, not a device registry. MAX_DEVICES is
therefore only a SOFT limit on activations. A real per-device limit needs a backend; for strictly
device-bound licenses use a manual serial bound to a Machine ID.
"""

import base64
import datetime
import hashlib
import hmac
import json
import os
import platform
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

GUMROAD_PRODUCT_ID = "CaXSd_0DfUN7Actk_WBoJg=="  # HMZ Video Studio Pro Gumroad product_id
GUMROAD_BUY_URL = "https://hmzbytes.gumroad.com/l/video-studio-pro"
FREE_OPERATIONS = 5               # free exports before activation is required
MAX_DEVICES = 3                   # SOFT limit on Gumroad activations (uses counter), not a device registry
REVERIFY_DAYS = 7
OFFLINE_GRACE_DAYS = 14
PRODUCT_CODE = "VSP"
# Public keys (Base64 raw Ed25519). `tools/issue_serial.py keygen` writes them here automatically.
SERIAL_PUBLIC_KEY_B64 = "pKCd5CutTNaZBC9MgUd4NM71PKXExHQLHBx4f0kImwI="
REVOKE_PUBLIC_KEY_B64 = "7ThWiLGkVhbqtS96vIu2Q92HB7kTxbKgOGzOb7e/8cE="
PAYMENT_PUBLIC_KEY_B64 = "mfLV8rxP+431B9TIc/yunVtbbn3VV+eqC5ioQY/I3ok="
UPDATE_PUBLIC_KEY_B64 = "8jm7k1fXiwsFZXUgs6TKICyckDNrT4ipYv8KGG8y6BA="

DEFAULT_UPDATE_URL = "https://raw.githubusercontent.com/HMZ67993/Video-Studio-Pro/refs/heads/main/Update.json"

_HMAC_PART_A = b"HMZ_VSP_2026_CORE_STATE_"
_HMAC_PART_B = b"9f8e7d6c5b4a392817263544_GUARD"

SERIAL_FORMAT_VERSION = 1
HEX_LEN_SHA256 = 64


class NetworkError(Exception):
    """Raised when network connectivity fails during Gumroad verification (never means 'invalid key')."""


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------
def _b64u_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64u_decode(text: str) -> bytes:
    pad = "=" * ((4 - len(text) % 4) % 4)
    return base64.urlsafe_b64decode((text + pad).encode("ascii"))


def canonical_json(obj: Any) -> bytes:
    """Canonical JSON used for every signature: UTF-8, sorted keys, fixed separators, no NaN/Infinity."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _reject_constant(name: str) -> Any:
    raise ValueError(f"invalid JSON constant {name}")


def _load_public_key(pub_b64: Optional[str]) -> Optional[Ed25519PublicKey]:
    key_str = (pub_b64 or "").strip()
    if not key_str:
        return None
    try:
        return Ed25519PublicKey.from_public_bytes(base64.b64decode(key_str))
    except Exception:
        return None


def _verify_sig(pub_b64: Optional[str], domain: str, message: bytes, sig_b64: str) -> bool:
    """Verify an Ed25519 signature over `f"{PRODUCT_CODE}-{domain}|" + message` (domain separation)."""
    pub = _load_public_key(pub_b64)
    if pub is None or not isinstance(sig_b64, str):
        return False
    try:
        pub.verify(_b64u_decode(sig_b64), f"{PRODUCT_CODE}-{domain}|".encode("utf-8") + message)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Machine ID & local state
# ---------------------------------------------------------------------------
def machine_id() -> str:
    raw_identifier = ""
    if platform.system().lower().startswith("win"):
        try:
            import winreg  # type: ignore

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),
            ) as key:
                val, _ = winreg.QueryValueEx(key, "MachineGuid")
                if val:
                    raw_identifier = str(val).strip()
        except Exception:
            pass
    if not raw_identifier:
        for candidate in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                if os.path.exists(candidate):
                    content = Path(candidate).read_text(encoding="utf-8").strip()
                    if content:
                        raw_identifier = content
                        break
            except Exception:
                pass
    if not raw_identifier:
        raw_identifier = f"{uuid.getnode()}-{socket.gethostname()}"
    digest = hashlib.sha256(f"HMZ-{PRODUCT_CODE}-{raw_identifier}".encode("utf-8")).hexdigest().upper()
    short = digest[:16]
    return f"{short[0:4]}-{short[4:8]}-{short[8:12]}-{short[12:16]}"


def _get_state_paths(custom_dir: Optional[Path] = None) -> Tuple[Path, Path]:
    if custom_dir is not None:
        base_a = Path(custom_dir) / "primary"
        base_b = Path(custom_dir) / "backup"
    else:
        appdata = os.environ.get("APPDATA") or str(Path.home() / ".config")
        localappdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
        base_a = Path(appdata) / "HMZVideoStudioPro"
        base_b = Path(localappdata) / "HMZVideoStudioPro_Guard"
    base_a.mkdir(parents=True, exist_ok=True)
    base_b.mkdir(parents=True, exist_ok=True)
    return base_a / "lic_state.dat", base_b / "lic_mirror.dat"


def _compute_hmac(payload_dict: Dict[str, Any]) -> str:
    secret = _HMAC_PART_A + _HMAC_PART_B + machine_id().encode("utf-8")
    return hmac.new(secret, canonical_json(payload_dict), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Manual (offline) serials:  CODE1-<payload_b64>.<signature_b64>
# payload = canonical JSON {v,p,m,iat,nbf,e,cid,name,jti};  signed message = "<CODE>-LIC1|" + payload bytes
# ---------------------------------------------------------------------------
def _valid_payload(payload: Any) -> bool:
    if not isinstance(payload, dict) or payload.get("v") != SERIAL_FORMAT_VERSION:
        return False
    for k in ("p", "m", "jti"):
        if not isinstance(payload.get(k), str) or not payload[k] or len(payload[k]) > 64:
            return False
    for k in ("iat", "nbf"):
        if not isinstance(payload.get(k), int) or isinstance(payload.get(k), bool):
            return False
    e = payload.get("e")
    if e is not None and (not isinstance(e, int) or isinstance(e, bool)):
        return False
    for k in ("cid", "name"):
        if k in payload and (not isinstance(payload[k], str) or len(payload[k]) > 120):
            return False
    return True


def verify_manual_serial(
    serial_str: str,
    current_machine_id: Optional[str] = None,
    revoked_list: Optional[List[str]] = None,
    pub_key_b64: Optional[str] = None,
    expected_product: str = PRODUCT_CODE,
    now_ts: Optional[float] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Return (status, payload). status: ok | invalid | product | device | not_yet_valid | expired | disabled."""
    serial = (serial_str or "").strip()
    if "-" not in serial or "." not in serial or len(serial) > 2048:
        return "invalid", {}
    prefix, rest = serial.split("-", 1)
    if not prefix.endswith("1") or rest.count(".") != 1:
        return "invalid", {}
    payload_b64, sig_b64 = rest.split(".")
    try:
        payload_bytes = _b64u_decode(payload_b64)
    except Exception:
        return "invalid", {}
    if not _verify_sig(pub_key_b64 if pub_key_b64 is not None else SERIAL_PUBLIC_KEY_B64, "LIC1", payload_bytes, sig_b64):
        return "invalid", {}  # includes serials of other products (different key / domain)
    try:
        payload = json.loads(payload_bytes.decode("utf-8"), parse_constant=_reject_constant)
    except (ValueError, UnicodeDecodeError):
        return "invalid", {}
    if not _valid_payload(payload):
        return "invalid", {}
    if payload["p"] != expected_product:
        return "product", {}
    revoked = set(revoked_list or [])
    if payload["jti"] in revoked or serial in revoked:
        return "disabled", payload
    dev_id = (current_machine_id or machine_id()).upper()
    if payload["m"] != "*" and payload["m"].upper() != dev_id:
        return "device", payload
    now = int(time.time() if now_ts is None else now_ts)
    if now < payload["nbf"]:
        return "not_yet_valid", payload
    if payload.get("e") is not None and now > payload["e"]:
        return "expired", payload
    return "ok", payload


# ---------------------------------------------------------------------------
# Gumroad
# ---------------------------------------------------------------------------
def verify_gumroad_key(
    license_key: str,
    product_id: Optional[str] = None,
    increment_uses: bool = True,
    timeout: float = 8.0,
) -> Tuple[str, Dict[str, Any]]:
    """Verify a Gumroad key. Raises NetworkError for connectivity/server problems (never reported as invalid).

    `increment_uses` must be True only for the real activation, never for periodic re-verification.
    """
    key_clean = (license_key or "").strip()
    pid = product_id if product_id is not None else GUMROAD_PRODUCT_ID
    if not key_clean:
        return "invalid", {}
    if not pid:
        return "not_configured", {}
    data = urllib.parse.urlencode(
        {"product_id": pid, "license_key": key_clean, "increment_uses_count": "true" if increment_uses else "false"}
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.gumroad.com/v2/licenses/verify",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "HMZVideoStudioPro/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "invalid", {}
        raise NetworkError(f"HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise NetworkError(str(e)) from e
    if not isinstance(body, dict):
        raise NetworkError("unexpected response")
    if not body.get("success"):
        return "invalid", {}
    purchase = body.get("purchase", {}) or {}
    if purchase.get("refunded") or purchase.get("chargebacked") or purchase.get("disputed"):
        return "disabled", body
    if purchase.get("subscription_cancelled_at") or purchase.get("subscription_failed_at") or purchase.get("subscription_ended_at"):
        return "expired", body
    try:
        uses = int(body.get("uses", 1))
    except (TypeError, ValueError):
        uses = 1
    if increment_uses and uses > MAX_DEVICES:
        return "device", body
    return "ok", body


# ---------------------------------------------------------------------------
# Signed data from update.json (revocation list, payment info, release info)
# ---------------------------------------------------------------------------
def verify_signed_revoked_list_or_none(update_data: Dict[str, Any], pub_key_b64: Optional[str] = None) -> Optional[List[str]]:
    """Validly signed (possibly empty) revocation list, else None."""
    if not isinstance(update_data, dict):
        return None
    revoked, sig = update_data.get("revoked"), update_data.get("revoked_sig")
    if not isinstance(revoked, list) or not all(isinstance(x, str) for x in revoked):
        return None
    try:
        msg = canonical_json(revoked)
    except (TypeError, ValueError):
        return None
    key = pub_key_b64 if pub_key_b64 is not None else REVOKE_PUBLIC_KEY_B64
    return list(revoked) if _verify_sig(key, "REVOKED1", msg, sig) else None


def verify_signed_revoked_list(update_data: Dict[str, Any], pub_key_b64: Optional[str] = None) -> List[str]:
    return verify_signed_revoked_list_or_none(update_data, pub_key_b64) or []


def verify_signed_payment_info(update_data: Dict[str, Any], pub_key_b64: Optional[str] = None) -> Optional[Dict[str, str]]:
    if not isinstance(update_data, dict):
        return None
    payment, sig = update_data.get("payment"), update_data.get("payment_sig")
    if not isinstance(payment, dict):
        return None
    try:
        msg = canonical_json(payment)
    except (TypeError, ValueError):
        return None
    key = pub_key_b64 if pub_key_b64 is not None else PAYMENT_PUBLIC_KEY_B64
    if not _verify_sig(key, "PAYMENT1", msg, sig):
        return None
    return {str(k): str(v) for k, v in payment.items()}


def verify_signed_release(update_data: Dict[str, Any], pub_key_b64: Optional[str] = None) -> Optional[Dict[str, str]]:
    """Return {version,url,sha256,notes} only if `update_sig` is valid and the fields are well-formed."""
    if not isinstance(update_data, dict):
        return None
    fields = {k: update_data.get(k) for k in ("version", "url", "sha256", "notes")}
    if not all(isinstance(v, str) for v in fields.values()):
        return None
    if not fields["url"].lower().startswith("https://"):
        return None
    sha = fields["sha256"].lower()
    if sha and (len(sha) != HEX_LEN_SHA256 or any(c not in "0123456789abcdef" for c in sha)):
        return None
    key = pub_key_b64 if pub_key_b64 is not None else UPDATE_PUBLIC_KEY_B64
    if not _verify_sig(key, "UPDATE1", canonical_json(fields), update_data.get("update_sig", "")):
        return None
    return {k: str(v) for k, v in fields.items()}


# ---------------------------------------------------------------------------
# License manager
# ---------------------------------------------------------------------------
class LicenseManager:
    def __init__(self, custom_storage_dir: Optional[Path] = None, pub_key_b64: Optional[str] = None, keys: Optional[Dict[str, str]] = None):
        self.custom_storage_dir = custom_storage_dir
        # `pub_key_b64` (tests) overrides all purposes; `keys` overrides individually.
        base = {
            "serial": SERIAL_PUBLIC_KEY_B64,
            "revoke": REVOKE_PUBLIC_KEY_B64,
            "payment": PAYMENT_PUBLIC_KEY_B64,
            "update": UPDATE_PUBLIC_KEY_B64,
        }
        if pub_key_b64 is not None:
            base = {k: pub_key_b64 for k in base}
        base.update(keys or {})
        self.keys = base
        self.pub_key_b64 = base["serial"]
        self.dev_id = machine_id()
        self.path_a, self.path_b = _get_state_paths(custom_storage_dir)
        self.update_cache_data: Dict[str, Any] = {}
        self.state = self._load_or_init_state()

    # ---- state -------------------------------------------------------------
    def _default_state(self) -> Dict[str, Any]:
        return {
            "activated": False,
            "license_type": "trial",
            "license_key": "",
            "customer": "",
            "jti": "",
            "nbf": 0,
            "exp": None,
            "used_operations": 0,
            "last_verified_iso": "",
            "last_seen_ts": 0,
            "tampered": False,
            "revoked_cache": [],
        }

    def _read_signed_file(self, path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        try:
            wrapper = json.loads(path.read_text(encoding="utf-8"))
            payload, sig = wrapper.get("payload"), wrapper.get("hmac")
            if not isinstance(payload, dict) or not isinstance(sig, str):
                return {"_tampered": True}
            if not hmac.compare_digest(sig, _compute_hmac(payload)):
                return {"_tampered": True}
            return payload
        except Exception:
            return {"_tampered": True}

    def _write_signed_state(self, state_dict: Dict[str, Any]) -> None:
        state_dict["last_seen_ts"] = max(int(state_dict.get("last_seen_ts", 0) or 0), int(time.time()))
        clean = {k: v for k, v in state_dict.items() if not k.startswith("_")}
        wrapper = json.dumps({"payload": clean, "hmac": _compute_hmac(clean)}, indent=2)
        for p in (self.path_a, self.path_b):
            try:
                tmp = p.with_suffix(p.suffix + ".tmp")
                tmp.write_text(wrapper, encoding="utf-8")
                os.replace(tmp, p)  # atomic
            except Exception:
                pass

    def _load_or_init_state(self) -> Dict[str, Any]:
        a, b = self._read_signed_file(self.path_a), self._read_signed_file(self.path_b)
        good = [x for x in (a, b) if x is not None and not x.get("_tampered")]
        if (a and a.get("_tampered")) or (b and b.get("_tampered")):
            if len(good) == 1:  # one copy intact: restore from it (counters take the max)
                merged = dict(self._default_state(), **good[0])
                self._write_signed_state(merged)
                return merged
            penalized = self._default_state()
            penalized["used_operations"] = FREE_OPERATIONS
            penalized["tampered"] = True
            self._write_signed_state(penalized)
            return penalized
        if a is not None and b is not None:
            merged = dict(self._default_state(), **a)
            merged["used_operations"] = max(int(a.get("used_operations", 0)), int(b.get("used_operations", 0)))
            merged["last_seen_ts"] = max(int(a.get("last_seen_ts", 0) or 0), int(b.get("last_seen_ts", 0) or 0))
            self._write_signed_state(merged)
            return merged
        existing = a if a is not None else b
        state = dict(self._default_state(), **(existing or {}))
        self._write_signed_state(state)
        return state

    def effective_now(self) -> int:
        """Current time that can't go backwards past the last time the app ran (basic clock-rollback defence)."""
        return max(int(time.time()), int(self.state.get("last_seen_ts", 0) or 0))

    # ---- queries -------------------------------------------------------------
    def is_activated(self) -> bool:
        if not self.state.get("activated"):
            return False
        revoked = self.state.get("revoked_cache", [])
        if self.state.get("license_key") in revoked or (self.state.get("jti") and self.state["jti"] in revoked):
            self.state["activated"] = False
            self._write_signed_state(self.state)
            return False
        ltype = self.state.get("license_type")
        if ltype == "manual":
            now = self.effective_now()
            exp = self.state.get("exp")
            if now < int(self.state.get("nbf", 0) or 0) or (exp is not None and now > int(exp)):
                return False
        if ltype == "gumroad":
            last_iso = self.state.get("last_verified_iso", "")
            if last_iso:
                try:
                    if (datetime.date.today() - datetime.date.fromisoformat(last_iso)).days > OFFLINE_GRACE_DAYS:
                        return False
                except ValueError:
                    pass
        return True

    def license_summary(self) -> Dict[str, Any]:
        st = self.state
        exp = st.get("exp")
        return {
            "activated": self.is_activated(),
            "type": st.get("license_type", "trial"),
            "customer": st.get("customer", ""),
            "expires": datetime.datetime.fromtimestamp(int(exp), datetime.timezone.utc).date().isoformat() if exp else "",
            "tampered": bool(st.get("tampered")),
        }

    def remaining_free_operations(self) -> int:
        if self.is_activated():
            return 999999
        return max(0, FREE_OPERATIONS - int(self.state.get("used_operations", 0)))

    def can_perform_paid_operation(self) -> bool:
        return self.is_activated() or self.remaining_free_operations() > 0

    def consume_operation(self) -> bool:
        """Call only after a real, successful, state-changing operation."""
        if self.is_activated():
            return True
        if self.remaining_free_operations() <= 0:
            return False
        self.state["used_operations"] = int(self.state.get("used_operations", 0)) + 1
        self._write_signed_state(self.state)
        return True

    # ---- activation ------------------------------------------------------------
    def _activate_state(self, ltype: str, key: str, customer: str, **extra: Any) -> None:
        self.state.update(
            activated=True, license_type=ltype, license_key=key, customer=customer,
            last_verified_iso=datetime.date.today().isoformat(), tampered=False, **extra,
        )
        self._write_signed_state(self.state)

    def activate_key(self, raw_key: str) -> str:
        key = (raw_key or "").strip()
        if not key:
            return "invalid"
        revoked = self.state.get("revoked_cache", [])
        looks_manual = "." in key and "-" in key and key.split("-", 1)[0].endswith("1")
        if looks_manual:
            status, payload = verify_manual_serial(
                key, current_machine_id=self.dev_id, revoked_list=revoked, pub_key_b64=self.keys["serial"], now_ts=self.effective_now()
            )
            if status == "ok":
                self._activate_state(
                    "manual", key, str(payload.get("name") or payload.get("cid") or ""),
                    jti=payload["jti"], nbf=payload["nbf"], exp=payload.get("e"),
                )
            return status
        try:
            status, info = verify_gumroad_key(key, increment_uses=True)
        except NetworkError:
            return "network_error"
        if status == "ok":
            purchase = info.get("purchase", {}) if isinstance(info, dict) else {}
            self._activate_state("gumroad", key, str(purchase.get("email", "")), jti="", nbf=0, exp=None)
        return status

    def reverify_current_license(self) -> str:
        key = self.state.get("license_key", "")
        if not key:
            return "invalid"
        ltype = self.state.get("license_type", "")
        if ltype == "manual":
            status, _ = verify_manual_serial(
                key, current_machine_id=self.dev_id, revoked_list=self.state.get("revoked_cache", []),
                pub_key_b64=self.keys["serial"], now_ts=self.effective_now(),
            )
            if status != "ok":
                self.state["activated"] = False
                self._write_signed_state(self.state)
            return status
        if ltype == "gumroad":
            try:
                status, _ = verify_gumroad_key(key, increment_uses=False)  # never bump the counter on re-verification
            except NetworkError:
                return "network_error"
            if status == "ok":
                self.state["last_verified_iso"] = datetime.date.today().isoformat()
            else:
                self.state["activated"] = False
            self._write_signed_state(self.state)
            return status
        return "invalid"

    # ---- signed data ---------------------------------------------------------------
    def apply_update_json(self, update_data: Dict[str, Any]) -> None:
        """Cache update.json and apply the revocation list only if its signature is valid."""
        self.update_cache_data = update_data if isinstance(update_data, dict) else {}
        verified = verify_signed_revoked_list_or_none(self.update_cache_data, self.keys["revoke"])
        if verified is not None:
            self.state["revoked_cache"] = verified
            if self.state.get("license_key") in verified or (self.state.get("jti") and self.state["jti"] in verified):
                self.state["activated"] = False
            self._write_signed_state(self.state)

    def get_verified_payment_info(self) -> Optional[Dict[str, str]]:
        return verify_signed_payment_info(self.update_cache_data, self.keys["payment"])

    def get_verified_release(self) -> Optional[Dict[str, str]]:
        return verify_signed_release(self.update_cache_data, self.keys["update"])
