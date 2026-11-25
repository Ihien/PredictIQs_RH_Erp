@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 erp_rh.py %*) else (python erp_rh.py %*)
if errorlevel 1 echo. & echo Python 3 est requis : installez-le depuis https://www.python.org/downloads/ (cochez "Add Python to PATH").
pause
