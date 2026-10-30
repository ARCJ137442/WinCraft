# TeamSense model-quota window

This provider demonstrates a read-only floating quota panel using TeamSense's
documented `GET /v1/integrations/models` Agent API. It sends only a bearer token
with the existing `data:read` scope. It does not call refresh, admin, Codex
usage, or vendor APIs and does not store the token or response on disk.

## Data shown

- **DeepSeek:** cached CNY/USD balance values, kept as separate currencies.
- **MiniMax:** separate model and `interval`/`weekly` windows. Bars use only an
  explicit `remainingPercent`, or the provided remaining/total counts. Up to
  eight models are shown; any omitted models are counted in the panel.
- **Codex:** shown as unknown because this read-only endpoint does not provide
  Codex quota observations. The provider does not infer a balance from history.
- **Sub2API:** its management snapshot is not treated as a usage quota.

The Agent API also exposes a broad `/v1/dashboard` projection, but this provider
does not request it: that payload includes unrelated finance, project, and service
summaries, while `modelQuotas` does not identify an account or an explicit quota
window. It cannot safely substitute for a Codex quota endpoint.

The Agent API response includes cache freshness and upstream state. A failed
HTTP read is displayed separately from the cached source freshness; only the
redacted display projection is retained in provider memory. The route does not
expose a provider account ID, so the panel labels its scope as the current
TeamSense connection and does not claim account-level attribution or combine
different windows.

## Synthetic visual check

```powershell
python examples/integrations/model_quota/provider.py --runtime "<actual-runtime-descriptor>" --demo
```

Demo mode uses synthetic values and makes no network request. It opens one
temporary world and removes only that world when closed or when the demo ends.

## Live connection

Use a TeamSense API token that has only `data:read`. Set
`TEAM_SENSE_BASE_URL` to the intended API origin (the TeamSense Agent API
documentation currently uses `https://api.team.lingtu.org`) and make
`TEAM_SENSE_API_TOKEN` available to the provider process through a local secret
manager or protected launch environment. If the token is absent in an
interactive session, the provider asks for it with hidden input. Never put it
in a command argument, source file, screenshot, or evidence log.

```powershell
python examples/integrations/model_quota/provider.py --runtime "<actual-runtime-descriptor>"
```

Remote HTTP requires HTTPS. Plain HTTP is accepted only for an explicit
loopback IP, and redirects are refused so the bearer token cannot be forwarded
to another origin. The request has a six-second timeout and a one-MiB response
limit. This example has not been connected to a real TeamSense account; the
account identity and a Codex quota source remain unresolved.
