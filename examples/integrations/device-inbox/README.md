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

To show the synthetic projection on a real local Tauri host, pass the actual descriptor
shown by the manager to `provider.py`. It creates and destroys only its own invited test
world. No device, Android notification, relay, or external authentication channel is
used by this example.
