@echo off
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Setup complete. Double-click Start.bat to launch AI Coding Buddy.
pause
exit /b 0
:failed
echo Setup failed. Install Python 3.11 or later, then try again. Check your internet connection.
pause
exit /b 1
