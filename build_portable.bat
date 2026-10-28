@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
 echo Python 3.11+ is required to BUILD. The finished portable app does not require Python.
 exit /b 1
)
py -m venv .build-venv
if errorlevel 1 exit /b 1
call .build-venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 exit /b 1
python -m pip install -r requirements.txt "pyinstaller>=6.10,<7"
if errorlevel 1 exit /b 1
python -m unittest -q tests_next tests_preview_cache
if errorlevel 1 (
 echo Tests failed. Portable build stopped.
 exit /b 1
)
python -m PyInstaller --noconfirm --clean --onedir --windowed --name HushPhoto --collect-all customtkinter --collect-all pillow_heif --hidden-import win32com.client --hidden-import pythoncom --hidden-import pywintypes modern_ui.py
if errorlevel 1 exit /b 1
if not exist dist\HushPhoto\HushPhoto.exe exit /b 1
rem Set HUSH_AFC_TOOLS to the local AFC toolkit directory before building if needed.
if exist "%HUSH_AFC_TOOLS%\afcclient.exe" (
  if not exist "dist\HushPhoto\native" mkdir "dist\HushPhoto\native"
  copy /y "%HUSH_AFC_TOOLS%\*.exe" "dist\HushPhoto\native\" >nul
  if exist "%HUSH_AFC_TOOLS%\*.dll" copy /y "%HUSH_AFC_TOOLS%\*.dll" "dist\HushPhoto\native\" >nul
  echo Included AFC tools from configured location.
) else (
  echo WARNING: afcclient.exe not found; USB import will require the tools separately.
)
copy /y README.md dist\HushPhoto\README.md >nul
powershell -NoProfile -Command "Compress-Archive -Path 'dist\HushPhoto\*' -DestinationPath 'dist\HushPhoto-Windows-Portable.zip' -Force"
if errorlevel 1 exit /b 1
echo READY: dist\HushPhoto\HushPhoto.exe
exit /b 0
