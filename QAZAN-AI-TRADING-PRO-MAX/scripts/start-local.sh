#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  echo "[QAZAN] Creating .env from .env.example..."
  cp .env.example .env
fi

if [ ! -d "node_modules" ]; then
  echo "[QAZAN] Installing Node.js dependencies..."
  npm install
fi

if ! python3 -c "import fastapi, uvicorn, pandas, numpy, sklearn, xgboost, websockets" >/dev/null 2>&1; then
  echo "[QAZAN] Installing Python backend dependencies..."
  python3 -m pip install -r backend/requirements.txt
fi

echo "[QAZAN] Starting unified development server on http://localhost:3000 ..."
npm run dev
