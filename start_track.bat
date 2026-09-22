@echo off
title TRACK_Backend_Server

echo Starting T.R.A.C.K. Local Bridge...
start "TRACK_Backend_Server" /MIN cmd /c "title TRACK_Backend_Server & python TRACK.py"

echo Waiting for backend to initialize...
timeout /t 2 /nobreak >nul

echo Opening T.R.A.C.K. Interface...
start TRACK_UI.html

echo.
echo ==========================================================
echo T.R.A.C.K. UI is open in your browser.
echo Do not close this terminal while testing.
echo.
echo Press ANY KEY to stop the local bridge and close...
echo ==========================================================
pause >nul

echo Shutting down server...
taskkill /FI "WindowTitle eq TRACK_Backend_Server*" /T /F >nul
exit