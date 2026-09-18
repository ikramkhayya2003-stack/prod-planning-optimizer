@echo off
setlocal
cd /d "%~dp0production_optimizer_frontend_v3"
if not exist "node_modules" (
  echo Installing frontend dependencies...
  call npm ci
  if errorlevel 1 call npm install
)
npm run dev
endlocal
