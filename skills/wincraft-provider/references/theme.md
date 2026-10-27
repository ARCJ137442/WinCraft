# Scene theme tokens

Scene themes are optional, typed renderer inputs. They let a provider express a
source-app visual style while WinCraft keeps its identity and local controls intact.

## Capability and wire shape

After `hello`, require the host to advertise:

```python
client.require_capabilities(scene_features=('theme_tokens',))
```

Then attach only the token object to the scene:

```json
{
  "root": {"id": "root", "kind": "stack", "children": []},
  "data": {},
  "theme": {
    "background": "#111827",
    "foreground": "#F9FAFB",
    "accent": "#67E8F9",
    "font_scale": 1.0,
    "radius_px": 12,
    "spacing_px": 12
  }
}
```

The theme object accepts exactly six fields:

| Token | Bound |
|---|---|
| `background`, `foreground`, `accent` | `#RRGGBB`; foreground/background and accent/background contrast must each be at least 4.5:1 |
| `font_scale` | 0.9–2.0 |
| `radius_px`, `spacing_px` | Integer 0–32 |

The theme belongs to the whole scene and changes through `scene.replace`. `scene.patch`
changes the component tree and preserves the current theme. Older 0.3 hosts omit
`scene_features`; providers that need themes must fail closed before sending one.

## Trust and accessibility

The renderer applies tokens to the component scene. The host retains the title bar,
provider identity, connection state, action/error feedback, permission cues, and local
rescue controls. Themes cannot change the host name, hide trusted controls, or claim
that an action was authorized. The protocol does not accept arbitrary CSS, HTML,
JavaScript, fonts, SVGs, or remote assets.

The Rust host validates token syntax, bounds, and contrast before replacing a scene. A
rejected replacement leaves the old scene, data, revision, and lease unchanged. The
renderer independently falls back to host defaults if it receives malformed theme data.

OS high-contrast and reduced-motion preferences override scene tokens. The local user
can adjust text scale with Ctrl+Shift+Plus or Ctrl+Minus and reset it with Ctrl+0. That
preference is host-owned and shared across worlds; provider `font_scale` cannot override
it.

## Verification boundary

- Run `python examples/python/theme_demo.py --runtime "<actual descriptor>"` against a host that advertises `theme_tokens` to visually compare the host default, the synthetic theme, and an explicitly rejected low-contrast theme.
- `python examples/python/lease_probe.py --runtime "<actual descriptor>"` checks the
  real Rust host's advertised capability, valid tokens, low-contrast rejection,
  atomic state preservation, and continued lease validity.
- `python scripts/browser_smoke.py` checks the compiled renderer with a mock provider,
  including theme scoping, trusted chrome, user zoom, forced colors, and reduced motion.
- The Windows release still needs human verification under the user's actual high
  contrast, display scale, and keyboard preferences. Browser media emulation is not a
  native accessibility test.
