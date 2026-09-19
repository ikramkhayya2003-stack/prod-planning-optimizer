@echo off
setlocal
cd /d "%~dp0frontend"
if not exist "node_modules" (
  echo Installing frontend dependencies...
  call npm ci
  if errorlevel 1 call npm install
)
npm run dev
endlocal
