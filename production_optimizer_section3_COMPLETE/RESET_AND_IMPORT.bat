@echo off
setlocal
REM This script is inside backend; .venv is in the project root.
set "BACKEND_DIR=%~dp0"
set "PROJECT_DIR=%~dp0.."
if not exist "%PROJECT_DIR%\.venv\Scripts\python.exe" (
  echo [ERROR] Backend virtual environment not found:
  echo %PROJECT_DIR%\.venv
  pause
  exit /b 1
)
cd /d "%BACKEND_DIR%"
call "%PROJECT_DIR%\.venv\Scripts\activate.bat"
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Dependency installation failed.
  pause
  exit /b 1
)
python reset_and_import.py
if errorlevel 1 (
  echo [ERROR] Reset/import failed.
  pause
  exit /b 1
)
echo.
echo [OK] Database reset and V2 Excel import completed.
pause
endlocal
