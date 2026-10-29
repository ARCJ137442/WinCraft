---
title: Configuration pack status
updated_at: 2026-10-30
last_verified_at: 2026-10-30
protocol_baseline: 0.3
status: runtime-implemented-ui-unverified
audience: maintainer, provider-author
---

# Configuration pack status

The handoff package's `draft-2026-10-26` pack schema and examples are checked by the repository's offline contract validator. B06-01 export and B06-02 pure planning are VERIFIED at their L1-L2 scope. B06-03 adds a local Rust Host/internal-manager preview, explicit permission approval/re-preview, confirmed world creation and ledger-guarded rollback path; these are optional `0.4-preview.1` capabilities, not protocol 0.3 methods. The current-source Windows release builds and a real Python SDK hello/capability handshake passes, but Manager UI interaction remains PARTIAL/NOT_RUN after Computer Use could not capture the window state.

## Allowed meaning

A pack records layout/blueprint references, capability requirements, provider type hints, permissions to request, theme IDs and a fallback policy. A missing provider produces an explainable plan outcome; it does not install or execute anything.

## Rejected content

- bearer tokens, runtime descriptors, leases or session IDs;
- provider binaries or embedded executable payloads;
- install hooks, shell commands, arbitrary paths or path traversal;
- arbitrary CSS/HTML/JavaScript or remote resources.

The `adapter` field is only an external program reference with a SHA-256 and `separate-user-approval`; import never executes it. Inventory claims are not grants: the local manager may approve only a permission that a fresh source explicitly declared, and that approval invalidates the old preview by advancing generation. Import creates new worlds only after local confirmation; rollback is a separate confirmation and removes only unmodified, unjoined worlds still matching the in-memory import ledger.

The exporter/planner and Rust behavior coverage do not prove native Manager UI behavior. B06-03 A1/A2/A3 remain PARTIAL; B06-04's four source-state fixtures and sanitized sample pack are present, but a two-independent-user environment re-authorization run remains NOT_RUN.
