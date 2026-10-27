# Native window actions

WinCraft can mediate a small set of actions on existing windows owned by other
applications. This is separate from a provider changing its own world's window with
`window.configure`.

## Check support before creating a world

Only a native Tauri host advertises `external_window_actions`. Headless hosts do not.
Fail closed before `world.create`:

```python
client.require_capabilities(button_features=("external_window_actions",))
```

## Declare a bounded action

Attach a static selector to a button. The current application IDs are `obsidian` and
`traffic_monitor`. Operations are `activate`, `maximize`, `restore`, and `minimize`. The optional
`title_contains` is a case-insensitive substring limited to 128 characters.

```python
{
    "id": "open-source-window",
    "kind": "button",
    "props": {
        "label": "回到Obsidian Workspace",
        "action": "dashboard.focus",
        "native_window_action": {
            "application": "obsidian",
            "operation": "activate",
            "title_contains": "Obsidian Workspace",
        },
    },
    "children": [],
}
```

On activation, the host matches only visible top-level windows whose executable image
matches the registered application ID. A single match is selected directly. If several
windows match, the host may use the currently foreground matching window; otherwise it
fails and asks the provider to use a narrower title filter. It never chooses an arbitrary
window by enumeration order or launches the application. `activate` may still fail when Windows rejects foreground activation;
that failure is reported to the user, and the provider receives no interaction event.
After host success, the provider receives its ordinary static action and must send the
normal `action.result` acknowledgement.

## Keep the boundary narrow

Do not accept arbitrary executable paths, titles as executable selectors, shell strings,
AHK snippets, scripts, or remote URLs. Application IDs and operations are a host-owned
allowlist. A provider needing another application must wait for an explicit host
capability and a reviewed application mapping. A button without `native_window_action`
continues to route its static action directly to its provider as usual.
