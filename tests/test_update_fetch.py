import base64
import json
from urllib.error import URLError
from unittest.mock import patch

import video_studio_update as update


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, limit=-1):
        return self.body[:limit] if limit >= 0 else self.body


def test_github_contents_api_base64_payload_is_decoded():
    document = {"payment": {"price": "900 EGP"}, "payment_sig": "signature"}
    encoded = base64.b64encode(json.dumps(document).encode("utf-8")).decode("ascii")
    envelope = {"encoding": "base64", "content": encoded}

    parsed = update._parse_update_response(
        json.dumps(envelope).encode("utf-8"),
        "https://api.github.com/repos/HMZ67993/Video-Studio-Pro/contents/Update.json?ref=main",
    )

    assert parsed == document


def test_default_hmz_endpoint_has_raw_cdn_and_api_fallbacks():
    urls = update._update_url_candidates(
        "https://raw.githubusercontent.com/HMZ67993/Video-Studio-Pro/refs/heads/main/Update.json"
    )

    assert urls[0].endswith("refs/heads/main/Update.json")
    assert any("cdn.jsdelivr.net" in url for url in urls)
    assert any("api.github.com/repos/HMZ67993/Video-Studio-Pro/contents/Update.json" in url for url in urls)


def test_fetch_retries_known_mirror_when_first_raw_host_fails():
    document = {"version": "1.0.0", "payment": {"price": "900 EGP"}}
    body = json.dumps(document).encode("utf-8")
    with patch.object(update.urllib.request, "urlopen", side_effect=[URLError("raw host unavailable"), _Response(body)]) as mocked:
        result = update.fetch_update_json(
            "https://raw.githubusercontent.com/HMZ67993/Video-Studio-Pro/refs/heads/main/Update.json",
            timeout=1.0,
        )

    assert result == document
    assert mocked.call_count == 2
