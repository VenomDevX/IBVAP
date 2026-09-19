@echo off
rem IBVAP one-click start: Docker, Supabase, backend (8002), frontend (3001), Chrome.
rem Always replaces whatever is running on port 3001.
rem Options: start-ibvap.bat -Rebuild   (force a frontend rebuild)
rem          start-ibvap.bat -NoBrowser (do not open Chrome)

title IBVAP launcher
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-ibvap.ps1" %*
if errorlevel 1 (
    echo.
    echo IBVAP did not start. Read the message above, fix it, and run this file again.
    pause
    exit /b 1
)
rem Short pause so the summary can be read (works without a console, unlike timeout).
ping -n 6 127.0.0.1 >nul
exit /b 0
