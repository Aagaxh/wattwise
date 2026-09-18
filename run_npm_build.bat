@echo off
set "PATH=E:\hackothon\tools\node-v20.18.0-win-x64;E:\hackothon\tools\python;E:\hackothon\tools\python\Scripts;%PATH%"
cd /d "E:\hackothon\wattwise\frontend"
call "E:\hackothon\tools\node-v20.18.0-win-x64\npm.cmd" run build
