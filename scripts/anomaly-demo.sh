#!/usr/bin/env bash
# DEMO / SYNTHETIC statistical anomaly walkthrough. Fictional figures, not INEC results.
#
# Runs a separate API and site on their own ports (API 8002, web 5175) over a dedicated
# store in backend/var/anomaly-demo. It never touches your real data or the preview:
# the folder carries a marker, and cleanup refuses to delete a folder without it.
# ANOMALY_MIN_SAMPLES is left at its normal default (30).
#
#   DEMO_ADMIN_PASSWORD='choose-one' scripts/anomaly-demo.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ADMIN_EMAIL="${DEMO_ADMIN_EMAIL:-admin@verivote.ng}"
ADMIN_PASSWORD="${DEMO_ADMIN_PASSWORD:?Set DEMO_ADMIN_PASSWORD (12+ characters)}"
REVIEWER_EMAIL="reviewer@anomaly-demo.verivote.ng"
API_PORT=8002
WEB_PORT=5175

export APP_ENV=development
export DIRECTORY_SOURCE=demo
export DATABASE_URL=
export DEV_DATABASE_PATH=var/anomaly-demo/anomaly-demo.sqlite3
export EVIDENCE_LOCAL_DIR=var/anomaly-demo/evidence
export CORS_ORIGINS="http://localhost:${WEB_PORT}"

cd "$ROOT/backend"
.venv/bin/python -m app.evidence.ai.anomaly_demo cleanup
.venv/bin/python -m app.evidence.ai.anomaly_demo seed
VERIVOTE_ADMIN_PASSWORD="$ADMIN_PASSWORD" .venv/bin/python -m app.auth.create_admin \
  --email "$ADMIN_EMAIL" --name "Demo Admin"

.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" \
  --no-access-log &
API_PID=$!
trap 'kill $API_PID ${WEB_PID:-} 2>/dev/null || true' EXIT INT TERM
for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:${API_PORT}/api/v1/health" >/dev/null && break
  sleep 1
done

API="http://127.0.0.1:${API_PORT}/api/v1"
TOKEN=$(curl -sf "$API/auth/login" -H 'content-type: application/json' \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" |
  .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -sf "$API/admin/users" -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d "{\"email\":\"$REVIEWER_EMAIL\",\"display_name\":\"Demo Reviewer\",\"roles\":[\"reviewer\"],\"password\":\"$ADMIN_PASSWORD\"}" \
  >/dev/null && echo "Reviewer account: $REVIEWER_EMAIL (same password as the admin)"

cd "$ROOT/frontend"
VITE_API_BASE_URL="http://localhost:${API_PORT}/api/v1" \
  npx vite --port "$WEB_PORT" --strictPort &
WEB_PID=$!

echo
echo "Anomaly demo ready at http://localhost:${WEB_PORT} (DEMO / SYNTHETIC data)."
echo "Sign in as $REVIEWER_EMAIL, open Verification review, and pick a SYNTHETIC-ODD record."
echo "Press Ctrl+C to stop. Remove the data with:"
echo "  (cd backend && .venv/bin/python -m app.evidence.ai.anomaly_demo cleanup)"
wait
