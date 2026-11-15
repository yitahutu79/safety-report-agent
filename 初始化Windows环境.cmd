@echo off
setlocal
cd /d "%~dp0"

if exist "E:\Python313\python.exe" goto use_e_python

py -3.13 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)" >nul 2>nul
if not errorlevel 1 goto use_py

echo Python 3.13 was not found.
echo Install Python 3.13 and run this file again.
pause
exit /b 1

:use_e_python
"E:\Python313\python.exe" "tools\setup_windows.py"
goto result

:use_py
py -3.13 "tools\setup_windows.py"

:result
if not errorlevel 1 goto success
echo.
echo Windows environment setup failed. Keep the error message above.
pause
exit /b 1

:success
echo.
pause
