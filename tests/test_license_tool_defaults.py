from pathlib import Path
import sys

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
