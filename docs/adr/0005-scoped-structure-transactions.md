---
title: Scoped structure transactions and ancestor revocation
updated_at: 2026-10-28
last_verified_at: 2026-10-28
protocol_baseline: 0.4-preview.1
status: implementation-decision
audience: maintainer, provider-author
---

# Scoped structure transactions and ancestor revocation

## Decision

Keep stable protocol 0.3 unchanged. In the opt-in `0.4-preview.1` composition mode:

- A component-scope writer may apply one atomic batch of `props`, `insert`, `remove`, `replace`, and `move` operations only inside its fixed subtree root. It cannot remove/move that root, add interactive nodes, or target another scope. Scope-local data bindings are rewritten to the scope's namespace before commit.
- The world authority may call `scope.structure.patch` for unowned layout. It cannot patch inside a child subtree. It may move an intact child root/group between unowned layout parents or remove a parent containing child roots. Removing a scope root removes that grant and namespace in the same transaction and sends `scope.revoked` to its current readers/writer.
- A failed operation, invalid final scene, boundary crossing, or schema violation publishes neither scene changes nor revision changes.
- Releasing, disconnecting, expiring, or locally rescuing the world authority fences every child writer, advances each child generation/epoch, rotates its join grant, and publishes a final filtered stale snapshot to already authorized readers. The prior grant cannot reacquire a lease; recovery requires recreating the temporary composition world.
- Scope-only sessions receive server-filtered `scope.snapshot` updates. They never receive the complete composition snapshot as a transport shortcut.

## Rationale and limits

The root authority owns layout boundaries; child providers own the content and data inside their subtrees. Whole-scene transactions use a candidate clone and commit once, so failed cross-boundary operations cannot partially apply. Root deletion is an explicit revocation boundary. This preview still does not route interactive actions by scope owner, support cross-scope moves, or provide stable 0.3 semantics.

## Verification

Cover ownership and rollback in core invariants; use the Rust WebSocket integration test and `examples/python/scope_probe.py` to verify filtered live updates, structure changes, parent revocation, and cleanup. Re-run the full Windows CI after the implementation changes.
