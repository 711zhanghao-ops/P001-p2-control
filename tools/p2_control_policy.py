import base64
import json
import os
import re
import sys
import urllib.request

API = "https://api.github.com"
REPO = os.environ["GITHUB_REPOSITORY"]
PR = os.environ["PR_NUMBER"]
TOKEN = os.environ["GITHUB_TOKEN"]

ALLOWED = {
    "tools/p2_verify.py",
    ".github/workflows/p2-control-receiver.yml",
    "README.md",
    "EVIDENCE.md",
}


def fail(msg):
    print("POLICY FAIL: " + msg)
    sys.exit(1)


def get(url):
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def get_file(path, ref):
    data = get(f"{API}/repos/{REPO}/contents/{path}?ref={ref}")
    if data.get("encoding") != "base64":
        fail(f"{path}: unexpected encoding")
    return base64.b64decode(data["content"]).decode("utf-8")


def main():
    pr = get(f"{API}/repos/{REPO}/pulls/{PR}")
    head = pr["head"]["sha"]
    base = pr["base"]["sha"]
    changed = get(f"{API}/repos/{REPO}/pulls/{PR}/files?per_page=100")

    if not changed:
        fail("PR has no changed files")
    for item in changed:
        name = item["filename"]
        if name not in ALLOWED:
            fail(f"file not allowed in control PR: {name}")
        if item["status"] not in ("modified", "added"):
            fail(f"unsupported change status for {name}: {item['status']}")

    workflow = get_file(".github/workflows/p2-control-receiver.yml", head)
    verifier = get_file("tools/p2_verify.py", head)

    if re.search(r"^ {6,10}(expected_path|expected_text)\s*:", workflow, re.M):
        fail("workflow must not expose expected_path/expected_text as dispatch inputs")
    if "handoff_sha" not in workflow:
        fail("workflow missing handoff_sha input")
    if "EXPECTED_PATH: _gh_api_probe/p2/bidirectional_handoff.txt" not in workflow:
        fail("workflow missing fixed EXPECTED_PATH")
    if "EXPECTED_TEXT: P001 P2 minimal handoff" not in workflow:
        fail("workflow missing fixed EXPECTED_TEXT")

    checks = [
        ("FIXED_EXPECTED_PATH = '_gh_api_probe/p2/bidirectional_handoff.txt'", "verifier missing fixed path constant"),
        ("if args.expected_path != FIXED_EXPECTED_PATH:", "verifier does not reject non-fixed path"),
        ("if not args.expected_text.strip():", "verifier does not reject blank expected text"),
        ("accepted = verified and text_ok", "verifier acceptance is not strictly verified+text"),
    ]
    for needle, msg in checks:
        if needle not in verifier:
            fail(msg)

    print(f"POLICY PASS: PR #{PR}")
    print(f"base_sha={base}")
    print(f"head_sha={head}")
    print(f"policy_workflow_sha={os.environ.get('GITHUB_SHA', 'unknown')}")
    print("changed_files=" + ",".join(i["filename"] for i in changed))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## P2 Control Policy\n\n")
            f.write(f"- Result: PASS\n- PR: #{PR}\n- base: `{base}`\n- head: `{head}`\n")
            f.write("- files: " + ", ".join(i["filename"] for i in changed) + "\n")


if __name__ == "__main__":
    main()
