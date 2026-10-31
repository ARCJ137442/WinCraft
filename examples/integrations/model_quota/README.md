# Model quota HUD

This read-only Provider can combine TeamSense's cached DeepSeek/MiniMax projection
with an optional Codex quota probe authenticated by the local Codex profile. Each
source, currency, model and quota window keeps its own status and update time.
Unknown fields remain unknown; the HUD does not infer a balance from session
history.

## Data sources

- **TeamSense:** fixed `GET /v1/integrations/models` using a `data:read` token.
  It returns cached DeepSeek balance, MiniMax model windows and source freshness.
  It does not include an account ID or Codex quota. This Provider does not call
  refresh, admin or dashboard routes.
- **Codex:** disabled unless `--codex-quota` is supplied. It parses the bounded
  local `auth.json` only after opt-in, uses only `tokens.access_token` and
  `tokens.account_id` in memory, and ignores all other fields. It performs one
  fixed HTTPS GET to the ChatGPT usage route, then keeps only bounded
  primary/secondary quota windows. It does not use `refresh_token`, write the
  auth file, or display the account ID. It rechecks the account after the request
  and clears the previous quota if the login changed or can no longer be confirmed.
- **Sub2API:** its management snapshot is not treated as a usage quota.

The Codex route `https://chatgpt.com/backend-api/wham/usage` is an undocumented
ChatGPT backend route, not a stable public API contract. The adapter is therefore
opt-in and experimental; schema or authorization changes fail closed. Official
Codex usage information remains available from the account Usage page described
in [OpenAI's help article](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan).

## Run

Use `--demo` for a synthetic display and Host smoke. Demo mode makes no network
request and reads no credentials:

```powershell
python examples/integrations/model_quota/provider.py --runtime "<actual-runtime-descriptor>" --demo --duration-seconds 120
```

Run the local Codex source only:

```powershell
python examples/integrations/model_quota/provider.py --runtime "<actual-runtime-descriptor>" --codex-quota
```

By default, the Codex home is `CODEX_HOME` or `~/.codex`. To use another
explicit Codex home, pass `--codex-home <directory>` together with
`--codex-quota`. The option is an explicit request to read that directory's
`auth.json` and make the fixed read-only HTTPS request.

To combine Codex with TeamSense, configure `TEAM_SENSE_BASE_URL` for the
intended API origin and make `TEAM_SENSE_API_TOKEN` available through a local
secret manager or protected process environment; then add `--codex-quota`. If a
TeamSense token is absent in an interactive session, the Provider asks with
hidden input. Never put it in a command argument, source file, screenshot or
evidence log. Remote TeamSense HTTP requires HTTPS; redirects are refused.

The Codex request has a six-second timeout and a 256 KiB response limit. The
auth file has a one-MiB input limit. No live Codex or TeamSense request is part
of the synthetic tests; real data, endpoint availability, freshness and window
pixels still require separate verification.
