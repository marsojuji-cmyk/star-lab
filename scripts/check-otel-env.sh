#!/usr/bin/env bash
# Verify OTEL env for exact token metrics (does not start a collector).
set -euo pipefail
ENV_FILE="${GROK_LAB_DATA:-$HOME/.grok/lab}/otel.env"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE" 2>/dev/null || true
  set +a
  echo "loaded $ENV_FILE"
fi
ok=0
if [[ -n "${OTEL_EXPORTER_OTLP_ENDPOINT:-}" ]] && [[ "${OTEL_EXPORTER_OTLP_ENDPOINT}" != *"your-collector"* ]]; then
  echo "OK  OTEL_EXPORTER_OTLP_ENDPOINT=$OTEL_EXPORTER_OTLP_ENDPOINT"
  ok=1
else
  echo "MISS OTEL_EXPORTER_OTLP_ENDPOINT (edit ~/.grok/lab/otel.env — replace your-collector placeholder)"
fi
if [[ -n "${OTEL_EXPORTER_OTLP_HEADERS:-}" ]] && [[ "${OTEL_EXPORTER_OTLP_HEADERS}" != *"REPLACE"* ]]; then
  echo "OK  OTEL_EXPORTER_OTLP_HEADERS is set (value hidden)"
else
  echo "WARN OTEL_EXPORTER_OTLP_HEADERS unset or placeholder"
fi
if [[ "$ok" -eq 1 ]]; then
  echo "STATUS: env ready — relaunch grok to export grok_code.token.usage"
  exit 0
fi
echo "STATUS: not configured (local lab still works; token $ stays estimated)"
exit 1
