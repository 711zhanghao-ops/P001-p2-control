# P001 P2 controlled receiver

Minimal public control repository for the P2 file-exchange protocol acceptance.

This repository contains only:

- `tools/p2_verify.py`: read-only verifier with fixed expected path and strict state gating.
- `.github/workflows/p2-control-receiver.yml`: manually dispatched receiver.
- a synthetic handoff fixture on the `handoff` branch.

No formal P001 data, tokens, account information or production pointers are stored here.
The control branch is protected and changes require a pull request and review.
