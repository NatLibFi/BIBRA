#!/bin/bash

set -e
echo "Starting uvicorn server..."
uv run uvicorn bibra.main:app --host 0.0.0.0 --port 8000 2>/dev/null &
UVICORN_PID=$!
trap "kill $UVICORN_PID 2>/dev/null" EXIT
npm run cy:run

