#!/usr/bin/env bash
# A separate, seeded preview of VeriVote, for looking around with sample activity.
#
# It never touches your real data: it uses the fictional demo directory, its own SQLite
# file and evidence folder under backend/var/preview, and its own ports
# (API 8001, web 5174). Every run starts from a clean preview database.
#
#   PREVIEW_ADMIN_PASSWORD='choose-one' scripts/preview.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ADMIN_EMAIL="${PREVIEW_ADMIN_EMAIL:-admin@verivote.ng}"
ADMIN_PASSWORD="${PREVIEW_ADMIN_PASSWORD:?Set PREVIEW_ADMIN_PASSWORD (12+ characters)}"
API_PORT=8001
WEB_PORT=5174

export APP_ENV=development
export DIRECTORY_SOURCE=demo
export DEV_DATABASE_PATH=var/preview/preview.sqlite3
export EVIDENCE_LOCAL_DIR=var/preview/evidence
export ANOMALY_MIN_SAMPLES=10
export INCIDENT_SUBMISSIONS_PER_HOUR=0
export CORS_ORIGINS="http://localhost:${WEB_PORT}"

cd "$ROOT/backend"
rm -rf var/preview
mkdir -p var/preview

echo "Creating the preview admin and seeding results through the evidence workflow"
VERIVOTE_ADMIN_PASSWORD="$ADMIN_PASSWORD" .venv/bin/python -m app.auth.create_admin \
  --email "$ADMIN_EMAIL" --name "Preview Admin"
.venv/bin/python -m app.analytics.demo_seed

.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" \
  --no-access-log &
API_PID=$!
trap 'kill $API_PID ${WEB_PID:-} 2>/dev/null || true' EXIT INT TERM

for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:${API_PORT}/api/v1/health" >/dev/null && break
  sleep 1
done

.venv/bin/python scripts/seed_preview.py --api "http://127.0.0.1:${API_PORT}/api/v1" \
  --admin-email "$ADMIN_EMAIL" --admin-password "$ADMIN_PASSWORD"

cd "$ROOT/frontend"
VITE_API_BASE_URL="http://localhost:${API_PORT}/api/v1" \
  npx vite --port "$WEB_PORT" --strictPort &
WEB_PID=$!

echo
echo "Preview ready at http://localhost:${WEB_PORT} (demo data, not an official result)."
echo "Press Ctrl+C to stop both servers."
wait
