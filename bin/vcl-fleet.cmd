@echo off
setlocal
set "HERE=%~dp0"
set "SCRIPT=%HERE%..\lib\vincula-fleet.py"
if exist "%HERE%lib\vincula-fleet.py" set "SCRIPT=%HERE%lib\vincula-fleet.py"
if exist "%HERE%..\lib\vincula-fleet.py" set "SCRIPT=%HERE%..\lib\vincula-fleet.py"
py -3 "%SCRIPT%" %*
if errorlevel 9009 python "%SCRIPT%" %*
