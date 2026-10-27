---
title: Configuration pack status
updated_at: 2026-10-27
last_verified_at: 2026-10-27
protocol_baseline: 0.3
status: proposal-validated
audience: maintainer, provider-author
---

# Configuration pack status

The handoff package's `draft-2026-10-26` pack schema and examples are now checked by the repository's offline contract validator. This does not add a runtime import command.

## Allowed meaning

A pack records layout/blueprint references, capability requirements, provider type hints, permissions to request, theme IDs and a fallback policy. A missing provider produces an explainable plan outcome; it does not install or execute anything.

## Rejected content

- bearer tokens, runtime descriptors, leases or session IDs;
- provider binaries or embedded executable payloads;
- install hooks, shell commands, arbitrary paths or path traversal;
- arbitrary CSS/HTML/JavaScript or remote resources.

The `adapter` field is only an external program reference with a SHA-256 and `separate-user-approval`; it is not an execution instruction. Import, migration, preview, rollback and a real new-machine run remain future work. The current validator proves schema/fixture boundaries only.
