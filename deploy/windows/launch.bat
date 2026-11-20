@echo off
rem Manual launcher: reads .env from this folder, then starts the companion headless.
setlocal
cd /d "%~dp0"
if not exist ".env" (
  echo Missing .env - copy .env.example and fill in JONI_CLIENT_ID and JONI_BRIDGE_URL.
  exit /b 1
)
for /f "usebackq tokens=1,* delims==" %%A in (`findstr /v /b "#" ".env"`) do set "%%A=%%B"
if not defined JONI_CLIENT_ID (
  echo JONI_CLIENT_ID is empty in .env
  exit /b 1
)
if not defined JONI_BRIDGE_URL (
  echo JONI_BRIDGE_URL is empty in .env
  exit /b 1
)
start "" pythonw.exe -u companion.py
