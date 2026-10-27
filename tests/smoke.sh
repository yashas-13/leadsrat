#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
. ./.env
set +a
base=http://127.0.0.1:8787
test "$(curl -sS -o /dev/null -w '%{http_code}' "$base/health/ready")" = 200
test "$(curl -sS -o /dev/null -w '%{http_code}' "$base/api/v1/leads")" = 401
test "$(curl -sS -o /dev/null -w '%{http_code}' "$base/api/v1/team")" = 401
test "$(curl -sS -o /dev/null -w '%{http_code}' "$base/api/v1/team/overview")" = 401
test "$(curl -sS -o /dev/null -w '%{http_code}' "$base/api/v1/team/activity")" = 401
test "$(curl -sS -o /dev/null -w '%{http_code}' "$base/api/v1/leads/follow-ups")" = 401
test "$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$base/api/v1/leads" -H "X-API-Key: $LEADSRAT_API_KEY" -H 'Content-Type: application/json' -d '{"name":"Invalid Budget","budget_min_paise":200,"budget_max_paise":100}')" = 422
printf 'health, auth rejection (including team endpoint) and payload validation: PASS\n'
