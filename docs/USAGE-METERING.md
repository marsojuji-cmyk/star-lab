# Usage metering (exact token $)

## Status

| Source | Available now? |
|--------|----------------|
| Local session `signals.json` | Peak context, tools, streams — **not** full billable totals |
| `lab tokens audit` | Predicted horizon vs optional `actual_tokens` you log |
| OTEL export | **Not enabled** on this machine |
| GitHub remote | **Blocked** until `gh auth login` |

## Enable exact API token metrics (optional)

See Grok user guide `24-monitoring-usage.md`. Outline:

```bash
# Example env (point at YOUR collector — do not commit secrets)
export OTEL_EXPORTER_OTLP_ENDPOINT="https://your-collector.example/v1/metrics"
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer <token>"
# Then relaunch grok so grok_code.token.usage metrics flow out
```

Metrics of interest: `grok_code.token.usage` with `type` = input | output | reasoning | cache_read.

## Local discipline (works offline today)

```bash
lab tokens route "task…"
# … work …
lab tokens complete --audit-id ID --actual-tokens N --quality 0.0-1.0 --success yes
lab tokens audit --stats
lab tokens distill
```

## GitHub remote (blocked)

```bash
gh auth login
cd ~/Projects/grok-home
gh repo create grok-home --private --source=. --remote=github --push
# or: git remote add github git@github.com:USER/grok-home.git && git push -u github main
```

Until then `origin` remains local: `/Users/a100/Projects/grok-home-origin.git`.

## Local helper

```bash
# Edit endpoint first:
$EDITOR ~/.grok/lab/otel.env
bash ~/Projects/grok-home/scripts/check-otel-env.sh
```
