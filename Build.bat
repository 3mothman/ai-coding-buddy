@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" scripts\build_windows.py
if errorlevel 1 goto failed
echo Build complete. Open dist\AI-Coding-Buddy\AI-Coding-Buddy.exe.
pause
exit /b 0
:failed
echo Build failed. Review the messages above.
pause
exit /b 1
