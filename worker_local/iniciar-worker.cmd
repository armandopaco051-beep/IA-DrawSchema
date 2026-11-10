@echo off
cd /d "%~dp0.."
if not exist "worker_local\.env" (
  echo Primero ejecuta: .\venv\Scripts\python.exe -m worker_local.setup
  pause
  exit /b 1
)
"venv\Scripts\python.exe" -m worker_local.main
pause
