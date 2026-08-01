# OTEL for exact token metrics

1. Copy `env.example` → `~/.grok/lab/otel.env`
2. Set a real `OTEL_EXPORTER_OTLP_ENDPOINT`
3. `bash scripts/check-otel-env.sh`
4. `source ~/.grok/lab/otel.env && grok` (or export in shell profile)

Without a collector, lab + `lab tokens audit` still work offline.
