# P2 control evidence

Date: 2026-11-23 (UTC receipts)
Repository: `711zhanghao-ops/P001-p2-control`
Control branch: `main`

## Gate status

This repository uses a single-account, explicit-downgrade gate. It is **not** equivalent to an independent GitHub approving review, and no GitHub `Approve` from the reviewer is claimed.

- Require a pull request: enabled
- Required approvals: disabled (0)
- Require Code Owners review: disabled
- Require approval of the most recent push: disabled
- Required status check: `P2 Control Policy / verify-control-pr`
- Require branches up to date: enabled
- Require conversation resolution: enabled
- Require linear history: enabled
- Do not allow bypassing the above settings: enabled
- Allow force pushes: disabled
- Allow deletions: disabled

Reviewer opinion from the external session is recorded only as:

`EXTERNAL SESSION REVIEW — NOT A GITHUB APPROVING REVIEW`

## Trusted control version

- `main` after PR #1 merge: `c3aeb62a596d192556aea4e76cb826d5fff2a277`
- Control policy run for PR #1: `45171976948` (Success)
- PR #1: https://github.com/711zhanghao-ops/P001-p2-control/pull/1
- Policy gate added by PR #2 (`8cc58fd`), base-ref fix by PR #3.

## Fixed expected path

- Workflow env: `EXPECTED_PATH=_gh_api_probe/p2/bidirectional_handoff.txt`, `EXPECTED_TEXT=P001 P2 minimal handoff`
- Verifier: `FIXED_EXPECTED_PATH` constant; rejects non-fixed path; rejects blank expected text; `accepted = verified and text_ok`
- The receiver workflow accepts only `handoff_sha` as dispatch input.

## Final three runs on `main`

| Case | Run | Handoff commit | Result | State | Artifact | Receipt |
|---|---|---|---|---|---|---|
| Positive | 45172445945 | `e178b8be8548335091424db8d9eea16993a0bb45` | ACCEPTED | RECEIVED, VERIFIED, REVIEWED, ACCEPTED | 702 B, `sha256:79fcd151f78ba9a8c5b41e97fe66a9837f471c9c92056a5717d093ff617595c5` | 1,718 B, `1220D56ACA445047EAB9B2BA391092B59A3E00E209B5C5D0DCCB56BB890C33CC` |
| SHA tamper | 45172534517 | `546865ed2f62c6d9309504531f2aae91e364a090` | FAILED | RECEIVED only | 614 B, `sha256:6f88f4670f71815e0fecfbaa2d7231a9daa6e958ef720d57e03da10a981b9463` | 1,075 B, `F664739160125014B07E1696D6018C3DC41842E49EEC03B3246D79F412FC5E40` |
| Path mismatch | 45172614588 | `f269f28dbef107ba582d1bd54b0603bf27f471c5` | FAILED | RECEIVED only | 625 B, `sha256:9b893245d27afed67c9af80bd26d610400f6d2d5893f504851f6c55c25a86393` | 1,069 B, `82B835C28D0933C89FEDD25B1B1AD95520DAC0CA025AE2A41F8FC80A4B6463CE` |

SHA tamper receipt: `pathOk=true`, `sizeOk=true`, `shaOk=false`, `textOk=false`.
Path mismatch receipt: `pathOk=false`, `sizeOk=true`, `shaOk=true`, `textOk=false`.

## Policy v2 maintenance

- Maintenance window: required status check temporarily removed to bootstrap the policy script upgrade; restored immediately after merge.
- Policy enhancement commit: `c67f72d` (PR #5).
- Post-maintenance main: `3e10408ea949698676c914c4571b9ce57fd2a182`.
- New policy checks: isolated behavioral suite (positive, blank text, missing text, non-fixed path, SHA mismatch, path mismatch, text mismatch) plus a string-preserving bypass self-test.
- Verification PR: this EVIDENCE update (required `verify-control-pr` must pass before merge).

## Boundary

No formal P001 repository, production code, production data, production pointer or frozen copy was modified. P4 remains NOT AUTHORIZED. P2 acceptance covers the protocol only.
