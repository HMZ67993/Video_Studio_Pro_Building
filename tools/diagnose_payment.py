# -*- coding: utf-8 -*-
"""Safe diagnostic for HMZ Video Studio Pro manual-payment data loading."""
from __future__ import annotations
import json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from video_studio_license import LicenseManager, DEFAULT_UPDATE_URL, verify_signed_payment_info, verify_signed_release, verify_signed_revoked_list_or_none
    from video_studio_update import _update_url_candidates, _parse_update_response, load_cached_update, CACHE_NAME
except Exception as exc:
    print('IMPORT_ERROR:', type(exc).__name__, str(exc))
    raise SystemExit(2)

appdata = Path(os.environ.get('APPDATA') or (Path.home() / '.config')) / 'HMZVideoStudioPro'
settings_path = appdata / 'settings.json'
cache_path = appdata / CACHE_NAME
settings = {}
if settings_path.exists():
    try: settings = json.loads(settings_path.read_text(encoding='utf-8'))
    except Exception as exc: print('SETTINGS_READ_ERROR:', type(exc).__name__, str(exc))
url = str(settings.get('update_url') or DEFAULT_UPDATE_URL)
manager = LicenseManager()

lines = []
def log(k, v):
    lines.append(f'{k}: {v}')

log('APP_VERSION_CONTEXT', 'HMZ Video Studio Pro payment diagnostic')
log('PYTHON', sys.version.split()[0])
log('SETTINGS_FILE_EXISTS', settings_path.exists())
log('CONFIGURED_UPDATE_URL', url)
log('CACHE_FILE_EXISTS', cache_path.exists())
log('CACHE_FILE_SIZE', cache_path.stat().st_size if cache_path.exists() else 0)

remote_data = None
for endpoint in _update_url_candidates(url):
    if not endpoint.startswith('https://'):
        log('ENDPOINT', endpoint + ' | SKIPPED non-HTTPS')
        continue
    try:
        import urllib.request
        headers = {'User-Agent':'HMZVideoStudioPro-Diagnostic/1.0','Cache-Control':'no-cache','Pragma':'no-cache'}
        if 'api.github.com/repos/' in endpoint.lower():
            headers.update({'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
        req = urllib.request.Request(endpoint, headers=headers)
        started = time.time()
        with urllib.request.urlopen(req, timeout=12) as response:
            raw = response.read(600000)
            status = response.status
            content_type = response.headers.get('Content-Type','')
        elapsed = round(time.time()-started, 2)
        data = _parse_update_response(raw, endpoint)
        log('ENDPOINT_RESULT', f'{endpoint} | HTTP {status} | {len(raw)} bytes | {elapsed}s | content-type={content_type} | JSON={isinstance(data,dict)}')
        if isinstance(data, dict):
            remote_data = data
            break
    except Exception as exc:
        log('ENDPOINT_ERROR', f'{endpoint} | {type(exc).__name__}: {exc}')

if remote_data is not None:
    payment = verify_signed_payment_info(remote_data, manager.keys['payment'])
    release = verify_signed_release(remote_data, manager.keys['update'])
    revoked = verify_signed_revoked_list_or_none(remote_data, manager.keys['revoke'])
    log('REMOTE_PAYMENT_SIGNATURE_VALID', payment is not None)
    log('REMOTE_UPDATE_SIGNATURE_VALID', release is not None)
    log('REMOTE_REVOKED_SIGNATURE_VALID', revoked is not None)
    log('REMOTE_PAYMENT_FIELDS_PRESENT', sorted(payment.keys()) if payment else 'NO - signature invalid or payment missing')
else:
    log('REMOTE_RESULT', 'NO ENDPOINT RETURNED A VALID JSON OBJECT')

cached = load_cached_update(appdata)
if cached is not None:
    cp = verify_signed_payment_info(cached, manager.keys['payment'])
    log('CACHE_PAYMENT_SIGNATURE_VALID', cp is not None)
    log('CACHE_PAYMENT_FIELDS_PRESENT', sorted(cp.keys()) if cp else 'NO - cache has no valid payment section')
else:
    log('CACHE_RESULT', 'NO READABLE CACHE')

out = Path(__file__).resolve().parents[1] / 'payment_diagnostic.txt'
out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('\n'.join(lines))
print('\nReport saved to:', out)
print('This report does not include license serials, private keys, or bank-account values.')
