@echo off
rem Double-click to play a week for a playtest (see play.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0play.ps1" %*
pause
