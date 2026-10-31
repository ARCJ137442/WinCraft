# Model quota HUD

This read-only Provider shows Codex, DeepSeek, and MiniMax quota sources in one
WinCraft world. It never calls the TeamSense service. The implementation borrows two
separate TeamSense collection patterns: bounded Codex rollout event parsing and fixed,
read-only vendor endpoints. Each source keeps its own identity scope, freshness, state,
currency, model, and quota window. Missing values remain unknown.

## Data sources

- **Codex rollout snapshot:** `--codex-rollout-quota` scans a bounded set of recent
  `sessions/` and `archived_sessions/` JSONL tails. It parses only `event_msg` events
  whose payload type is `token_count`, then projects `rate_limits.primary` and an
  optional `secondary` window. It does not read conversation text, `auth.json`, the
  Codex state database, or contact the Codex App or any network service. A snapshot
  without a recent event remains visible with its age marked stale/expired. Current HUD
  thresholds are fresh through 5 minutes, stale through 60 minutes, then expired; these
  are presentation labels, not a Codex service guarantee.
- **Codex live quota:** `--codex-quota` is a separate opt-in experimental source. It
  reads only the needed access token and account ID from the local `auth.json` in memory
  and makes the existing fixed HTTPS GET. It does not refresh or write credentials and
  never projects the account ID or token. The backend route is undocumented, not a
  stable public API, and is not required for the local rollout source.
- **DeepSeek:** `--deepseek-quota` enables a fixed `GET
  https://api.deepseek.com/user/balance`; the Provider reads `DEEPSEEK_API_KEY` only
  after the flag is present. It projects bounded currency balances only.
- **MiniMax:** `--minimax-quota` enables a fixed `GET
  https://api.minimaxi.com/v1/token_plan/remains`; the Provider reads `MINIMAX_API_KEY`
  only after the flag is present. It projects bounded model and quota-window fields.

DeepSeek and MiniMax credentials must be supplied through a protected local process
environment or secret manager. Never put a key in an argument, source file, screenshot,
Provider scene, or evidence. The network adapters require HTTPS, reject redirects, use a
fixed origin, cap response size, and sanitize failures. No real key or live request is
used by the synthetic tests. Sub2API management data is deliberately excluded because
it is not a quota measurement.

## Run

Use synthetic values for a visual/Host smoke. Demo mode reads no credentials and makes
no network requests:

```powershell
python examples/integrations/model_quota/provider.py --runtime "<actual-runtime-descriptor>" --demo --duration-seconds 120
```

To exercise the release headless Rust Host without an existing runtime descriptor,
run the repository smoke. It creates an isolated loopback descriptor and synthetic
Codex rollout, then removes both after the Provider exits:

```powershell
python scripts/model_quota_headless_smoke.py
```

Read Codex rollout snapshots without network access:

```powershell
python examples/integrations/model_quota/provider.py --runtime "<actual-runtime-descriptor>" --codex-rollout-quota
```

Enable only configured vendor sources:

```powershell
$env:DEEPSEEK_API_KEY = "<provided-through-your-secret-manager>"
$env:MINIMAX_API_KEY = "<provided-through-your-secret-manager>"
python examples/integrations/model_quota/provider.py --runtime "<actual-runtime-descriptor>" --deepseek-quota --minimax-quota
```

Use `--codex-quota` only when the experimental live Codex source is explicitly wanted.
`--codex-quota` and `--codex-rollout-quota` are mutually exclusive; both can be
combined with DeepSeek or MiniMax. `--codex-home <directory>` selects the Codex home
for either Codex source. The default is `CODEX_HOME` or `~/.codex`.

The panel refreshes every 60 seconds by default (configurable from 10 to 300 seconds).
It retains an in-memory last-good vendor snapshot on temporary read failure and marks
it stale; nothing is persisted by this Provider. Pass `--duration-seconds 5` for a
bounded real-source protocol smoke; without that option the Provider remains active
until its world is closed or the process is stopped. Real account reads, source
freshness, the experimental Codex endpoint, and native window pixels remain separate
acceptance items.
