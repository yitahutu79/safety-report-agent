@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto ready
echo The Windows project environment is not initialized.
pause
exit /b 0

:ready
".venv\Scripts\python.exe" "tools\windows_workbench.py" stop
if errorlevel 1 goto failed
echo.
echo Workbench stopped.
pause
exit /b 0

:failed
echo.
echo Stop did not complete. Check the message above.
pause
exit /b 1
