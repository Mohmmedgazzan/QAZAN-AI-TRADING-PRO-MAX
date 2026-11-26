@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0\.."

if not exist ".env" (
  if exist ".env.example" (
    echo [QAZAN] Creating .env from .env.example...
    copy ".env.example" ".env" >nul
  )
)

if not exist "node_modules" (
  echo [QAZAN] Installing Node.js dependencies...
  call npm install
  if errorlevel 1 exit /b 1
)

python -c "import fastapi, uvicorn, pandas, numpy, sklearn, xgboost, websockets" >nul 2>&1
if errorlevel 1 (
  echo [QAZAN] Installing Python backend dependencies...
  python -m pip install -r backend\requirements.txt
  if errorlevel 1 exit /b 1
)

echo [QAZAN] Starting unified development server on http://localhost:3000 ...
call npm run dev
