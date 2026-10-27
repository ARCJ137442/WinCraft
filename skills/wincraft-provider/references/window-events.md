# Window state events

WinCraft can notify a provider about selected state changes on a world it has already
joined. These subscriptions belong to the current WebSocket session and grant no read
membership or write authority by themselves.

## Check and subscribe

Check the advertised event types before relying on them:

```python
client.require_capabilities(event_types=(
    "window.geometry_changed",
    "window.visibility_changed",
))
subscription = await client.subscribe_events(
    world_id,
    ("window.geometry_changed", "window.visibility_changed"),
)
```

`event.subscribe` requires prior membership in the world, including read-only membership.
It captures the current `sequence` and `window_revision` as the subscription baseline and
does not grant a lease. One session may hold at most 32 subscriptions. Unsubscribe with
`client.unsubscribe_events(subscription_id)`; subscriptions also end on world leave,
world destruction, or connection close.

## State delivery

The current event types are coalescible state:

- `window.geometry_changed`: latest geometry intent. A fixed `position` is expressed in
  physical desktop pixels; a semantic `anchor` uses one of the four current monitor work
  area corners with logical `margin_x` / `margin_y`. The host includes one of these
  placement forms together with width and height in logical pixels. Providers should
  treat `anchor` as intent and re-read the snapshot after reconnect; they must not turn
  the resolved native position back into a provider coordinate loop.
- `window.visibility_changed`: the world window's logical `visible` setting.

Events arrive as `{"event":"window.event","data":...}` with an event ID, subscription
ID, world ID, type, delivery class, source, optional cause ID, world sequence,
`window_revision`, and a minimal payload. Sequence gaps are allowed: providers should
adopt the newest state and must not expect every drag frame. A `cause_id` correlates the
immediate RPC request or internal interaction that produced a provider/operator change;
it is not an idempotency key. Human/system changes may have no cause ID.

The shared Python client keeps its event queue bounded and replaces adjacent queued state
updates for the same subscription/type with the newest sequence. It preserves intervening
occurrence messages such as `interaction` and `world.deleted` in order.

Window state events are observations. They do not trigger host actions, and subscribing
does not authorize `window.configure`, cross-application actions, or any other write.
The provider must still hold the current writer lease for writes. The host has no
automatic event-to-action rules, so a provider should avoid writing the same state back
unless its own rule has a clear stop condition. Button `interaction` events remain a
separate action channel; a slow WebSocket consumer receives `resync_required` and must
reconnect/rebuild rather than assume an interaction was delivered.

## Consume and clean up

```python
try:
    while True:
        message = await client.events.get()
        if message.get("event") != "window.event":
            continue
        data = message["data"]
        if data["subscription_id"] == subscription["subscription_id"]:
            print(data["type"], data["sequence"], data["payload"])
finally:
    await client.unsubscribe_events(subscription["subscription_id"])
```

Do not persist subscription IDs across reconnect. Rejoin, read a fresh snapshot, and
register a new subscription after verifying the new session and host ID.
