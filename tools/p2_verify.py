import argparse
import datetime
import hashlib
import json
import os
import sys


def fail(msg):
    print(msg)
    raise SystemExit(3)


def safe_rel(path):
    if not path or not isinstance(path, str):
        return False
    if path.startswith(('/', '\\')) or ':' in path:
        return False
    parts = path.replace('\\', '/').split('/')
    if any(p in ('', '.', '..', '.git') for p in parts):
        return False
    return True


FIXED_EXPECTED_PATH = '_gh_api_probe/p2/bidirectional_handoff.txt'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--expected-path', required=True)
    ap.add_argument('--expected-text', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    if args.expected_path != FIXED_EXPECTED_PATH:
        fail('expected_path must equal the fixed control path')
    if not args.expected_text.strip():
        fail('expected_text must be non-empty')

    manifest_rel = '_gh_api_probe/p2/handoff_manifest.json'
    manifest_path = os.path.join(args.root, manifest_rel)
    try:
        manifest = json.load(open(manifest_path, encoding='utf-8-sig'))
    except Exception as exc:
        fail(f'manifest parse failed: {exc}')

    declared = str(manifest.get('path', ''))
    expected = FIXED_EXPECTED_PATH
    path_ok = declared == expected and safe_rel(declared)
    file_path = os.path.join(args.root, expected) if safe_rel(expected) else ''
    file_exists = bool(file_path) and os.path.isfile(file_path)
    data = open(file_path, 'rb').read() if file_exists else b''
    size = len(data)
    sha = hashlib.sha256(data).hexdigest().upper()
    manifest_size = int(manifest.get('size', -1))
    manifest_sha = str(manifest.get('sha256', '')).upper()
    size_ok = file_exists and manifest_size == size
    sha_ok = file_exists and manifest_sha == sha
    verified = path_ok and file_exists and size_ok and sha_ok

    text_ok = False
    if verified and args.expected_text:
        try:
            text = open(file_path, 'rb').read().decode('utf-8', errors='replace')
            text_ok = args.expected_text in text
        except Exception:
            text_ok = False

    now = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat()
    identity = 'github-actions:' + os.environ.get('GITHUB_RUN_ID', 'unknown')
    states = []
    if file_exists:
        states.append({'state': 'RECEIVED', 'by': identity, 'at': now, 'evidence': f'manifest parsed; file found at {expected}'})
    if verified:
        states.append({'state': 'VERIFIED', 'by': identity, 'at': now, 'evidence': f'path={expected}; size {size}; sha256 {sha}; all matched'})
    if verified and text_ok:
        states.append({'state': 'REVIEWED', 'by': identity, 'at': now, 'evidence': f'expected text found: {args.expected_text}'})
        states.append({'state': 'ACCEPTED', 'by': identity, 'at': now, 'evidence': 'controlled receiver acceptance'})

    accepted = verified and text_ok
    receipt = {
        'receiptSchemaVersion': 'P2-RECEIPT-v1.0',
        'role': 'receiver',
        'receiverIdentity': identity,
        'stage': 'File',
        'branch': os.environ.get('HANDOFF_BRANCH', ''),
        'commit': os.environ.get('HANDOFF_SHA', ''),
        'expectedPath': expected,
        'manifestDeclaredPath': declared,
        'pathOk': path_ok,
        'fileExists': file_exists,
        'fileBytes': size,
        'fileSha256': sha,
        'manifestSize': manifest_size,
        'manifestSha256': manifest_sha,
        'sizeOk': size_ok,
        'shaOk': sha_ok,
        'textOk': text_ok,
        'receivedAt': now,
        'status': 'ACCEPTED' if accepted else 'FAILED',
        'error': '' if accepted else 'path/file/manifest mismatch',
        'states': states,
        'finishedAt': now,
    }
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    if not accepted:
        raise SystemExit(3)


if __name__ == '__main__':
    main()
