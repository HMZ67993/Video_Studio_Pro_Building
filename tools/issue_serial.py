#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HMZ Video Studio Pro - developer licensing, release-signing and manifest tool (DEVELOPER ONLY).

Never ship this folder or tools/keys/ to customers. All messages are English on purpose (Windows console).

Commands:
  keygen [--force]                         create Ed25519 keys (serial, revoke, payment, update, manifest)
                                           and write the PUBLIC keys into the app source
  issue --machine ID|* --customer NAME [--cid ID] [--days N | --expires YYYY-MM-DD] [--nbf YYYY-MM-DD]
  revoke --jti JTI | --serial SERIAL       add to the signed revocation list and rebuild update.json
  sign-payment [--price ...]               update and sign payment info, rebuild update.json
  release --version V --url HTTPS_URL [--sha256 HEX] [--notes TEXT]   sign release info, rebuild update.json
  manifest --dir DIR [--version V]         create+sign DIR/integrity.json for a build folder
  build                                    rebuild tools/output/update.json from the current state
  products-template                        write tools/output/products.json sample
  list                                     list issued serials
"""

import argparse
import base64
import datetime
import hashlib
import json
import os
import re
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

TOOLS_DIR = Path(os.path.abspath(__file__)).parent
PROJECT_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from video_studio_license import PRODUCT_CODE, SERIAL_FORMAT_VERSION, _b64u_encode, canonical_json  # noqa: E402

KEYS_DIR = TOOLS_DIR / "keys"
OUTPUT_DIR = TOOLS_DIR / "output"
STATE_FILE = TOOLS_DIR / "state.json"
LICENSE_PY = PROJECT_ROOT / "video_studio_license.py"
INTEGRITY_PY = PROJECT_ROOT / "video_studio_integrity.py"

PURPOSES = ("serial", "revoke", "payment", "update", "manifest")
# purpose -> (file to patch, constant name)
PUBLIC_KEY_TARGETS = {
    "serial": (LICENSE_PY, "SERIAL_PUBLIC_KEY_B64"),
    "revoke": (LICENSE_PY, "REVOKE_PUBLIC_KEY_B64"),
    "payment": (LICENSE_PY, "PAYMENT_PUBLIC_KEY_B64"),
    "update": (LICENSE_PY, "UPDATE_PUBLIC_KEY_B64"),
    "manifest": (INTEGRITY_PY, "MANIFEST_PUBLIC_KEY_B64"),
}


def die(msg: str, code: int = 1) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------------------
def default_state() -> Dict[str, Any]:
    return {
        "version": "1.0.0",
        "download_url": "https://hmzbytes.gumroad.com/l/Video_Studio_Pro",
        "sha256": "",
        "notes": "الإصدار الأول / The first release",
        "revoked": [],
        "issued": [],
        # Preserve the seller payment details supplied for HMZ Video Studio Pro.
        "payment": {
            "price": "500 جنيه مصري",
            "bank_name": "CIB",
            "bank_account": "100040309367",
            "instapay": "01150362890",
            "wallet": "01557783633",
            "whatsapp": "201150362890",
        },
    }


def load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            st = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return {**default_state(), **st}
        except Exception:
            die(f"state file is corrupted: {STATE_FILE}")
    return default_state()


def save_state(state: Dict[str, Any]) -> None:
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_FILE)


def load_private(purpose: str) -> Ed25519PrivateKey:
    path = KEYS_DIR / f"{purpose}.key"
    if not path.exists():
        die(f"private key '{purpose}' not found. Run: keygen")
    return Ed25519PrivateKey.from_private_bytes(base64.b64decode(path.read_text(encoding="utf-8").strip()))


def sign(purpose: str, domain: str, message: bytes) -> str:
    return _b64u_encode(load_private(purpose).sign(f"{PRODUCT_CODE}-{domain}|".encode("utf-8") + message))


def patch_constant(path: Path, name: str, value: str) -> None:
    text = path.read_text(encoding="utf-8")
    new, n = re.subn(rf'^{name}\s*=\s*"[^"]*"', f'{name} = "{value}"', text, flags=re.MULTILINE)
    if n != 1:
        die(f"could not patch {name} in {path.name}")
    path.write_text(new, encoding="utf-8")


# ---------------------------------------------------------------------------
def cmd_keygen(force: bool = False) -> None:
    if KEYS_DIR.exists() and any(KEYS_DIR.glob("*.key")):
        if not force:
            die("keys already exist. Re-running would invalidate every issued serial. Use --force to replace (a backup is kept).")
        backup = KEYS_DIR.parent / f"keys_backup_{int(time.time())}"
        shutil.copytree(KEYS_DIR, backup)
        print(f"[INFO] old keys backed up to {backup}")
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    for purpose in PURPOSES:
        priv = Ed25519PrivateKey.generate()
        raw_priv = priv.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        raw_pub = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        (KEYS_DIR / f"{purpose}.key").write_text(base64.b64encode(raw_priv).decode("ascii"), encoding="utf-8")
        pub_b64 = base64.b64encode(raw_pub).decode("ascii")
        (KEYS_DIR / f"{purpose}.pub").write_text(pub_b64, encoding="utf-8")
        target, const = PUBLIC_KEY_TARGETS[purpose]
        patch_constant(target, const, pub_b64)
        print(f"[OK] {purpose}: public key written to {target.name}:{const}")
    cmd_build()
    print("[DONE] Private keys are in tools/keys/ - back them up OFFLINE and never commit or ship them.")


def to_ts(date_str: str, end_of_day: bool = False) -> int:
    try:
        d = datetime.date.fromisoformat(date_str)
    except ValueError:
        die(f"bad date '{date_str}', expected YYYY-MM-DD")
    dt = datetime.datetime.combine(d, datetime.time(23, 59, 59) if end_of_day else datetime.time(0, 0, 0), tzinfo=datetime.timezone.utc)
    return int(dt.timestamp())


def cmd_issue(machine: str, customer: str, cid: str = "", days: int = 0, expires: str = "", nbf: str = "", print_serial: bool = True) -> str:
    now = int(time.time())
    payload: Dict[str, Any] = {
        "v": SERIAL_FORMAT_VERSION,
        "p": PRODUCT_CODE,
        "m": (machine or "*").strip(),
        "iat": now,
        "nbf": to_ts(nbf) if nbf else now,
        "e": None,
        "cid": (cid or customer or "customer")[:100],
        "name": (customer or "Customer")[:100],
        "jti": uuid.uuid4().hex[:16],
    }
    if expires:
        payload["e"] = to_ts(expires, end_of_day=True)
    elif days > 0:
        payload["e"] = payload["nbf"] + days * 86400
    if payload["e"] is not None and payload["e"] <= payload["nbf"]:
        die("expiry must be after the start date")
    body = canonical_json(payload)
    serial = f"{PRODUCT_CODE}{SERIAL_FORMAT_VERSION}-{_b64u_encode(body)}.{sign('serial', 'LIC1', body)}"
    state = load_state()
    state["issued"].append({"jti": payload["jti"], "customer": payload["name"], "machine": payload["m"], "nbf": payload["nbf"], "exp": payload["e"], "serial": serial})
    save_state(state)
    if print_serial:
        print(serial)
    return serial


def jti_from_serial(serial: str) -> str:
    try:
        payload_b64 = serial.split("-", 1)[1].split(".")[0]
        pad = "=" * ((4 - len(payload_b64) % 4) % 4)
        return str(json.loads(base64.urlsafe_b64decode(payload_b64 + pad))["jti"])
    except Exception:
        die("cannot read jti from that serial")
        return ""


def cmd_revoke(jti: str = "", serial: str = "") -> Path:
    j = jti.strip() or jti_from_serial(serial.strip())
    state = load_state()
    if j and j not in state["revoked"]:
        state["revoked"].append(j)
    save_state(state)
    out = cmd_build()
    print(f"[OK] revoked {j}. Upload {out} to the public updates repository.")
    return out


def cmd_sign_payment(**kw: str) -> Path:
    state = load_state()
    for k in ("price", "bank_name", "bank_account", "instapay", "wallet", "whatsapp"):
        if kw.get(k):
            state["payment"][k] = kw[k]
    save_state(state)
    return cmd_build()


def cmd_release(version: str, url: str, sha256: str = "", notes: str = "") -> Path:
    if not url.lower().startswith("https://"):
        die("release url must be https://")
    if sha256 and (len(sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in sha256)):
        die("sha256 must be 64 hex characters")
    state = load_state()
    state.update(version=version, download_url=url, sha256=sha256.lower(), notes=notes or state.get("notes", ""))
    save_state(state)
    return cmd_build()


def cmd_build() -> Path:
    state = load_state()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    release = {"version": state["version"], "url": state["download_url"], "sha256": state.get("sha256", ""), "notes": state.get("notes", "")}
    doc = {
        **release,
        "update_sig": sign("update", "UPDATE1", canonical_json(release)),
        "revoked": state["revoked"],
        "revoked_sig": sign("revoke", "REVOKED1", canonical_json(state["revoked"])),
        "payment": state["payment"],
        "payment_sig": sign("payment", "PAYMENT1", canonical_json(state["payment"])),
    }
    out = OUTPUT_DIR / "update.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote {out}")
    return out


def cmd_manifest(directory: str, version: str = "") -> Path:
    base = Path(directory).resolve()
    if not base.is_dir():
        die(f"not a directory: {base}")
    files: Dict[str, Dict[str, Any]] = {}
    for p in sorted(base.rglob("*")):
        if p.is_file() and p.name != "integrity.json" and p.suffix.lower() not in (".log", ".tmp"):
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            files[p.relative_to(base).as_posix()] = {"sha256": h.hexdigest(), "size": p.stat().st_size}
    if not files:
        die("no files found to hash")
    ver = version or load_state()["version"]
    signed = {"version": ver, "files": files}
    manifest = {**signed, "sig": sign("manifest", "MANIFEST1", canonical_json(signed))}
    out = base / "integrity.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote {out} ({len(files)} files). Do not modify or re-sign any listed file afterwards.")
    return out


def cmd_products_template() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sample = {"products": [{"id": "example", "name_ar": "اسم التطبيق", "name_en": "App name", "desc_ar": "وصف", "desc_en": "Description",
                            "version": "1.0.0", "price": "$10", "url": "https://hmzbytes.gumroad.com/l/example"}]}
    out = OUTPUT_DIR / "products.json"
    out.write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote {out} (public file - host it in the public updates repository)")
    return out


def cmd_list() -> None:
    for it in load_state()["issued"]:
        exp = datetime.datetime.fromtimestamp(it["exp"], datetime.timezone.utc).date().isoformat() if it.get("exp") else "perpetual"
        print(f"{it['jti']}  {it['customer']:<24} machine={it['machine']:<20} expires={exp}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keygen")
    k.add_argument("--force", action="store_true")
    i = sub.add_parser("issue")
    i.add_argument("--machine", default="*")
    i.add_argument("--customer", default="Customer")
    i.add_argument("--cid", default="")
    i.add_argument("--days", type=int, default=0)
    i.add_argument("--expires", default="")
    i.add_argument("--nbf", default="")
    r = sub.add_parser("revoke")
    r.add_argument("--jti", default="")
    r.add_argument("--serial", default="")
    p = sub.add_parser("sign-payment")
    for f in ("price", "bank-name", "bank-account", "instapay", "wallet", "whatsapp"):
        p.add_argument(f"--{f}", default="")
    rel = sub.add_parser("release")
    rel.add_argument("--version", required=True)
    rel.add_argument("--url", required=True)
    rel.add_argument("--sha256", default="")
    rel.add_argument("--notes", default="")
    m = sub.add_parser("manifest")
    m.add_argument("--dir", required=True)
    m.add_argument("--version", default="")
    sub.add_parser("build")
    sub.add_parser("products-template")
    sub.add_parser("list")
    a = ap.parse_args()
    if a.cmd == "keygen":
        cmd_keygen(a.force)
    elif a.cmd == "issue":
        if not a.machine:
            die("--machine is required (use * for any device)")
        cmd_issue(a.machine, a.customer, a.cid, a.days, a.expires, a.nbf)
    elif a.cmd == "revoke":
        if not (a.jti or a.serial):
            die("give --jti or --serial")
        cmd_revoke(a.jti, a.serial)
    elif a.cmd == "sign-payment":
        cmd_sign_payment(price=a.price, bank_name=a.bank_name, bank_account=a.bank_account, instapay=a.instapay, wallet=a.wallet, whatsapp=a.whatsapp)
    elif a.cmd == "release":
        cmd_release(a.version, a.url, a.sha256, a.notes)
    elif a.cmd == "manifest":
        cmd_manifest(a.dir, a.version)
    elif a.cmd == "build":
        cmd_build()
    elif a.cmd == "products-template":
        cmd_products_template()
    elif a.cmd == "list":
        cmd_list()
    return 0


if __name__ == "__main__":
    sys.exit(main())
