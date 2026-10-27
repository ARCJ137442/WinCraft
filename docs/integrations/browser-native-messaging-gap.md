---
title: Browser Native Messaging bridge boundary
updated_at: 2026-10-27
last_verified_at: 2026-10-27
protocol_baseline: 0.3
status: blocked-external-source
audience: maintainer, browser-bridge-author
---

# Browser Native Messaging bridge boundary

This is the B05-01 decision and gap record. No browser extension, Native Messaging host manifest, fixed extension ID, or pairing authorization is present in this checkout. The document specifies the security boundary without claiming that a bridge exists.

## Invariants already enforced by WinCraft

- The transport binds loopback only.
- Discovery and WebSocket require `Authorization: Bearer <token>`.
- Requests carrying an `Origin` header are rejected, including localhost origins.
- A browser page must never receive the runtime descriptor or bearer token.
- The current renderer does not open arbitrary URLs or execute page code.

## Required bridge design before implementation

1. The native host keeps the descriptor and bearer token; the extension page receives only bounded semantic responses.
2. The host accepts one fixed extension identity and an explicit user pairing record. An extension update or pairing change invalidates the old grant.
3. Native Messaging messages use a strict schema with bounded size, request ID, source tab/session, expiry and allowed semantic operations. No raw WebSocket forwarding, HTML, JavaScript, shell command, cookie, or arbitrary URL is accepted.
4. The bridge connects to the loopback WebSocket with the existing bearer token and no browser `Origin`; it does not weaken `transport.rs`.
5. Tab close, navigation, extension restart, pairing revoke and bridge disconnect produce stale state and destroy/rebuild only the bridge-owned world. They never retain live data after the source session expires.

## Current status

- **BLOCKED**: fixed extension ID, host manifest, pairing authorization and a real browser source are missing.
- **PASS (existing host boundary)**: Rust transport Origin rejection and bearer checks are covered by transport tests and the real headless probe.
- **NOT_RUN**: Native Messaging process, extension permissions, pairing/revoke UI, tab lifecycle and stale projection.

Do not open a browser port or copy a runtime descriptor to a page to make a demo pass. Implement the bridge only after the source extension, version, permissions and user authorization are explicit.
