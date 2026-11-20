@echo off
rem Launcher for the Windows Scheduled Task on .12. No secrets here.
set JONI_CLIENT_ID=1530105931482791956
set JONI_BRIDGE_URL=http://100.82.26.92:1919/
set JONI_CLEAR_AFTER=3
cd /d "%~dp0"
start "" pythonw.exe -u companion.py
