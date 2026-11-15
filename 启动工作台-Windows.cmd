@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto ready
echo The Windows project environment is not initialized.
echo Run the Windows setup script first.
pause
exit /b 1

:ready
".venv\Scripts\python.exe" "tools\windows_workbench.py" start
if errorlevel 1 goto failed
echo.
echo Workbench started. The browser should open automatically.
echo You may close this window; the workbench will keep running.
pause
exit /b 0

:failed
echo.
echo Startup did not complete. Check the message above.
pause
exit /b 1
