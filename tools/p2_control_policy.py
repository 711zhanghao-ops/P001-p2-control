import ast
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

API = "https://api.github.com"
REPO = os.environ["GITHUB_REPOSITORY"]
PR = os.environ["PR_NUMBER"]
TOKEN = os.environ["GITHUB_TOKEN"]
MARKER = "P001 P2 minimal handoff"
FIXED_PATH = "_gh_api_probe/p2/bidirectional_handoff.txt"

ALLOWED = {
    "tools/p2_verify.py",
    ".github/workflows/p2-control-receiver.yml",
    "README.md",
    "EVIDENCE.md",
}

BANNED_IMPORTS = {
    "subprocess", "socket", "urllib", "http", "requests", "ctypes",
    "multiprocessing", "pty", "ftplib", "telnetlib", "smtplib", "asyncio",
}
BANNED_NAMES = {"eval", "exec", "compile", "__import__"}
BANNED_ATTRS = {
    ("os", "system"), ("os", "popen"), ("os", "execv"), ("os", "execve"),
    ("os", "spawnv"), ("os", "spawnve"), ("os", "fork"),
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


def scan_source(source):
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        fail(f"verifier does not parse: {exc}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in BANNED_IMPORTS:
                    fail(f"verifier imports banned module: {alias.name}")
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in BANNED_IMPORTS:
                fail(f"verifier imports banned module: {node.module}")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in BANNED_NAMES:
                fail(f"verifier calls banned function: {node.func.id}")
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name):
                    pair = (node.func.value.id, node.func.attr)
                    if pair in BANNED_ATTRS:
                        fail(f"verifier calls banned function: {pair[0]}.{pair[1]}")


def make_fixture(root, manifest_path, manifest_sha=None):
    d = os.path.join(root, "_gh_api_probe", "p2")
    os.makedirs(d, exist_ok=True)
    content = (MARKER + "\n" + "x" * 200)[:180]
    file_path = os.path.join(d, "bidirectional_handoff.txt")
    with open(file_path, "wb") as f:
        f.write(content.encode("utf-8"))
    actual = hashlib.sha256(content.encode("utf-8")).hexdigest().upper()
    manifest = {
        "path": manifest_path,
        "size": len(content),
        "sha256": manifest_sha if manifest_sha is not None else actual,
    }
    with open(os.path.join(d, "handoff_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f)


def run_case(verifier_path, name, expected_path, expected_text, manifest_path,
             manifest_sha=None, omit_text=False):
    with tempfile.TemporaryDirectory() as root:
        make_fixture(root, manifest_path, manifest_sha)
        out = os.path.join(root, "receipt.json")
        cmd = [sys.executable, "-I", "-S", verifier_path, "--root", root,
               "--expected-path", expected_path, "--out", out]
        if not omit_text:
            cmd.extend(["--expected-text", expected_text])
        env = {
            "PATH": "/usr/bin:/bin",
            "PYTHONIOENCODING": "utf-8",
            "HANDOFF_BRANCH": "handoff",
            "HANDOFF_SHA": "policy-test",
        }
        proc = subprocess.run(cmd, cwd=root, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=10)
        receipt = None
        if os.path.exists(out):
            try:
                with open(out, encoding="utf-8") as f:
                    receipt = json.load(f)
            except Exception as exc:
                return f"{name}: receipt not parseable: {exc}"
        return {"name": name, "proc": proc, "receipt": receipt}


def require_failed(r, name):
    if r["proc"].returncode == 0:
        return f"{name}: expected non-zero exit, got 0"
    if r["receipt"] and r["receipt"].get("status") == "ACCEPTED":
        return f"{name}: produced ACCEPTED"
    return None


def states(r):
    return {s.get("state") for s in (r["receipt"] or {}).get("states", [])}


def run_suite(source, label):
    violations = []
    with tempfile.TemporaryDirectory() as d:
        vp = os.path.join(d, "verifier.py")
        with open(vp, "w", encoding="utf-8") as f:
            f.write(source)
        try:
            scan_source(source)
        except SystemExit as exc:
            return [f"{label}: security scan failed ({exc})"]

        positive = run_case(vp, f"{label}/positive", FIXED_PATH, MARKER, FIXED_PATH)
        if not positive["receipt"] or positive["receipt"].get("status") != "ACCEPTED":
            violations.append(f"{label}/positive: not ACCEPTED")
        else:
            required = {"RECEIVED", "VERIFIED", "REVIEWED", "ACCEPTED"}
            if not required.issubset(states(positive)):
                violations.append(f"{label}/positive: missing states {sorted(required - states(positive))}")

        for name, kwargs in [
            ("blank-text", dict(expected_path=FIXED_PATH, expected_text="   ", manifest_path=FIXED_PATH)),
            ("missing-text", dict(expected_path=FIXED_PATH, expected_text="", manifest_path=FIXED_PATH, omit_text=True)),
            ("nonfixed-path", dict(expected_path="_gh_api_probe/p2/other.txt", expected_text=MARKER, manifest_path=FIXED_PATH)),
        ]:
            r = run_case(vp, f"{label}/{name}", **kwargs)
            err = require_failed(r, f"{label}/{name}")
            if err:
                violations.append(err)

        r = run_case(vp, f"{label}/sha-mismatch", FIXED_PATH, MARKER, FIXED_PATH, "0" * 64)
        rec = r["receipt"] or {}
        if rec.get("status") != "FAILED" or rec.get("shaOk") is not False:
            violations.append(f"{label}/sha-mismatch: wrong receipt")
        if {"REVIEWED", "ACCEPTED"} & states(r):
            violations.append(f"{label}/sha-mismatch: reached review/accept")

        r = run_case(vp, f"{label}/path-mismatch", FIXED_PATH, MARKER, "_gh_api_probe/p2/other.txt")
        rec = r["receipt"] or {}
        if rec.get("status") != "FAILED" or rec.get("pathOk") is not False:
            violations.append(f"{label}/path-mismatch: wrong receipt")
        if {"REVIEWED", "ACCEPTED"} & states(r):
            violations.append(f"{label}/path-mismatch: reached review/accept")

        r = run_case(vp, f"{label}/text-mismatch", FIXED_PATH, "not-present", FIXED_PATH)
        rec = r["receipt"] or {}
        if rec.get("status") != "FAILED" or rec.get("textOk") is not False:
            violations.append(f"{label}/text-mismatch: wrong receipt")
        if {"REVIEWED", "ACCEPTED"} & states(r):
            violations.append(f"{label}/text-mismatch: reached review/accept")

    return violations


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

    if "FIXED_EXPECTED_PATH = '_gh_api_probe/p2/bidirectional_handoff.txt'" not in verifier:
        fail("verifier missing fixed path constant")
    if "if args.expected_path != FIXED_EXPECTED_PATH:" not in verifier:
        fail("verifier does not reject non-fixed path")
    if "if not args.expected_text.strip():" not in verifier:
        fail("verifier does not reject blank expected text")

    violations = run_suite(verifier, "candidate")
    if violations:
        fail("behavioral suite failed: " + " | ".join(violations))

    bypass = verifier.replace(
        "accepted = verified and text_ok",
        "accepted = verified  # accepted = verified and text_ok",
    )
    if bypass == verifier:
        fail("policy self-test could not construct bypass case")
    bypass_violations = run_suite(bypass, "byte-preserving-bypass")
    if not bypass_violations:
        fail("policy self-test did not detect a string-preserving acceptance bypass")
    print("POLICY SELF-TEST PASS: detected " + " | ".join(bypass_violations[:2]))

    print(f"POLICY PASS: PR #{PR}")
    print(f"base_sha={base}")
    print(f"head_sha={head}")
    print(f"policy_workflow_sha={os.environ.get('GITHUB_SHA', 'unknown')}")
    print("changed_files=" + ",".join(i["filename"] for i in changed))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## P2 Control Policy\n\n")
            f.write(f"- Result: PASS (behavioral suite + bypass self-test)\n")
            f.write(f"- PR: #{PR}\n- base: `{base}`\n- head: `{head}`\n")
            f.write("- files: " + ", ".join(i["filename"] for i in changed) + "\n")
            f.write(f"- policy workflow commit: `{os.environ.get('GITHUB_SHA', 'unknown')}`\n")


if __name__ == "__main__":
    main()
