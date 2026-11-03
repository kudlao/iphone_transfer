@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
 echo ERROR: Python launcher not found. Install Python first.
 pause
 exit /b 1
)
rem Dependencies need to be installed only once; avoid pip/network work on every launch.
py -c "import customtkinter, PIL, pillow_heif" >nul 2>nul
if errorlevel 1 (
 echo Installing missing requirements...
 py -m pip --disable-pip-version-check install -r requirements.txt
 if errorlevel 1 (
  echo ERROR: Dependencies could not be installed.
  pause
  exit /b 1
 )
)
echo Starting Hush Photo from source...
py modern_ui.py
if errorlevel 1 (
 echo ERROR: Hush Photo exited with an error.
 pause
 exit /b 1
)
exit /b 0
