@echo off
setlocal
set "PROJECT_DIR=%~dp0"
set "BACKEND_DIR=%~dp0backend"
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
python -m app.create_db
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
endlocal
