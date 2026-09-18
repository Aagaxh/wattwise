@echo off
title WattWise Backend API Server
echo ====================================================
echo Starting WattWise Python Flask REST API Server...
echo ====================================================
set "PATH=E:\hackothon\tools\node-v20.18.0-win-x64;E:\hackothon\tools\python;E:\hackothon\tools\python\Scripts;%PATH%"
cd /d "E:\hackothon\wattwise\backend"
"E:\hackothon\tools\python\python.exe" app.py
pause
