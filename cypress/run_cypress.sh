#!/bin/bash

set -e
echo "Starting uvicorn server on port 24272 (BIBRA on a phone keypad)..."
uv run uvicorn bibra.main:app --host 0.0.0.0 --port 24272 2>/dev/null &
UVICORN_PID=$!
trap "kill $UVICORN_PID 2>/dev/null" EXIT
sleep 1
export CYPRESS_BASE_URL=http://localhost:24272
npm run cy:run

