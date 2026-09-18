@echo off 
title WattWise - React Frontend Dev Server 
set PATH=E:\hackothon\tools\node-v20.18.0-win-x64;%PATH% 
cd /d E:\hackothon\wattwise\frontend 
call E:\hackothon\tools\node-v20.18.0-win-x64\npm.cmd run dev 
pause
