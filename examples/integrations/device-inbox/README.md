# Device Inbox: synthetic authenticated-transport boundary

This is the B09-01 envelope and inbox policy prototype. `protocol/device-message.schema.json`
is `draft-2026-10-29`, not a protocol 0.3 host method. The inbox does not open a network
listener and does not route through a relay. It accepts a message only when a caller
supplies an out-of-band `TransportReceipt` from an already-authenticated external
transport adapter. A boolean or peer ID inside the message itself is never proof of
authentication.

The source identity is `(origin.device_id, origin.source_id, origin.source_instance_id,
message_id)`. `relay_trace` is delivery metadata only. Direct delivery requires the
authenticated peer to equal the origin device; relayed delivery additionally requires
the external transport to attest the origin. The prototype applies the earlier of the
origin-issued TTL deadline and the local receipt TTL deadline, keeps source sequence
ordering while accepting out-of-order arrival, rejects sequence reuse, and removes or
rejects messages after source revocation.

Only a bounded redacted `summary` crosses into the renderable projection. The schema
does not allow a raw body field, and the shared component tree has no reply, approval,
or write actions. The synthetic receipt helper is for tests only; it is not a transport
authenticator or evidence of a real phone connection.

## Verify

From the repository root:

```powershell
python -m unittest tests.test_device_inbox -v
python scripts/check_contracts.py
```

## Unified pending view (B09-03)

`unified_inbox.py` merges device messages with Agent activity into one pending
view. It combines two already-normalized, read-only sources; it does not open a
listener, authenticate a transport, or add a host method.

Three rules define the merge:

- **De-duplication is by source identity** `(device_id, source_id,
  source_instance_id, item_id)`, never by text similarity. The same item
  re-delivered through another relay hop collapses into one entry; two entries
  that merely read alike stay separate.
- **Pending lanes stay separate**: `needs_reply`, `needs_decision` and
  `notification`. An Agent waiting on approval is a decision item, not an
  approval grant.
- **Body text grants nothing.** A message body may contain an instruction; it
  stays display content. The merged projection carries no control
  capabilities, and a reply is offered as a copyable draft that still needs
  separate authorization to send.

The projection is rebuildable and never becomes business truth: both sources
remain authoritative for their own records.

```powershell
python -m unittest tests.test_unified_inbox -v
```

To show the synthetic projection on a real local Tauri host, pass the actual descriptor
shown by the manager to `provider.py`. It creates and destroys only its own invited test
world. No device, Android notification, relay, or external authentication channel is
used by this example.
