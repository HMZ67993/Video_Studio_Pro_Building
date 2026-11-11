from pathlib import Path
import base64
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import issue_serial


def test_default_payment_details_are_preserved_for_hmz_video_studio_pro():
    payment = issue_serial.default_state()["payment"]
    assert payment == {
        "price": "500 جنيه مصري",
        "bank_name": "CIB",
        "bank_account": "100040309367",
        "instapay": "01150362890",
        "wallet": "01557783633",
        "whatsapp": "201150362890",
    }


def test_default_update_target_matches_supplied_repository():
    from video_studio_license import DEFAULT_UPDATE_URL
    assert DEFAULT_UPDATE_URL == (
        "https://raw.githubusercontent.com/HMZ67993/Video-Studio-Pro/refs/heads/main/Update.json"
    )


def test_sync_public_keys_uses_existing_pairs_without_regenerating(tmp_path, monkeypatch):
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    targets = {}
    expected = {}
    for purpose in issue_serial.PURPOSES:
        private = Ed25519PrivateKey.generate()
        private_raw = private.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        public_raw = private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        (keys_dir / f"{purpose}.key").write_text(base64.b64encode(private_raw).decode("ascii"), encoding="utf-8")
        pub_b64 = base64.b64encode(public_raw).decode("ascii")
        (keys_dir / f"{purpose}.pub").write_text(pub_b64, encoding="utf-8")
        target = tmp_path / f"{purpose}_target.py"
        constant = f"{purpose.upper()}_PUBLIC_KEY_B64"
        target.write_text(f'{constant} = "stale-value"\n', encoding="utf-8")
        targets[purpose] = (target, constant)
        expected[purpose] = pub_b64

    monkeypatch.setattr(issue_serial, "KEYS_DIR", keys_dir)
    monkeypatch.setattr(issue_serial, "PUBLIC_KEY_TARGETS", targets)

    changed = issue_serial.sync_public_keys()

    assert len(changed) == len(issue_serial.PURPOSES)
    for purpose, (target, constant) in targets.items():
        assert f'{constant} = "{expected[purpose]}"' in target.read_text(encoding="utf-8")


def test_sync_public_keys_refuses_mismatched_pair_without_patching(tmp_path, monkeypatch):
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    targets = {}
    for purpose in issue_serial.PURPOSES:
        private = Ed25519PrivateKey.generate()
        private_raw = private.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        public_raw = private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        (keys_dir / f"{purpose}.key").write_text(base64.b64encode(private_raw).decode("ascii"), encoding="utf-8")
        (keys_dir / f"{purpose}.pub").write_text(base64.b64encode(public_raw).decode("ascii"), encoding="utf-8")
        target = tmp_path / f"{purpose}_target.py"
        constant = f"{purpose.upper()}_PUBLIC_KEY_B64"
        target.write_text(f'{constant} = "keep-this-value"\n', encoding="utf-8")
        targets[purpose] = (target, constant)

    # Break the first pair's public half; the tool must fail closed.
    first = issue_serial.PURPOSES[0]
    (keys_dir / f"{first}.pub").write_text(base64.b64encode(b"X" * 32).decode("ascii"), encoding="utf-8")
    monkeypatch.setattr(issue_serial, "KEYS_DIR", keys_dir)
    monkeypatch.setattr(issue_serial, "PUBLIC_KEY_TARGETS", targets)

    import pytest
    with pytest.raises(SystemExit):
        issue_serial.sync_public_keys()
    assert all('"keep-this-value"' in path.read_text(encoding="utf-8") for path, _ in targets.values())
