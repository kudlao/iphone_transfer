@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo.
echo ===== Hush Photo - portable Windows build =====
echo Source: %CD%
echo.
where py >nul 2>nul
if errorlevel 1 (
 echo ERROR: Python launcher "py" is not installed.
 exit /b 1
)
echo [1/5] Preparing reusable virtual environment...
if not exist ".build-venv\Scripts\python.exe" (
 py -m venv .build-venv
 if errorlevel 1 goto :failed
)
set "PY=.build-venv\Scripts\python.exe"
"%PY%" -c "import sys; print('Python:',sys.version.split()[0])"
if errorlevel 1 goto :failed

echo.
echo [2/5] Checking dependencies...
rem Do not upgrade pip on every build; it can stall behind a network connection.
"%PY%" -m pip --disable-pip-version-check install -r requirements.txt "pyinstaller>=6.10,<7"
if errorlevel 1 goto :failed

echo.
echo [3/5] Running regression and Tk interface smoke tests...
"%PY%" -m unittest -q tests_next tests_preview_cache test_media_groups tests_iphone_scan test_ui_smoke
if errorlevel 1 (
 echo ERROR: Tests failed. No portable package was created.
 goto :failed
)

echo.
echo [4/5] Building portable EXE...
echo NOTE: Close any running HushPhoto.exe before rebuilding.
rem Preserve PyInstaller analysis cache for faster subsequent builds.
"%PY%" -m PyInstaller --noconfirm --onedir --windowed --name HushPhoto --collect-all customtkinter --collect-all pillow_heif --hidden-import win32com.client --hidden-import pythoncom --hidden-import pywintypes modern_ui.py
if errorlevel 1 goto :failed
if not exist "dist\HushPhoto\HushPhoto.exe" (
 echo ERROR: HushPhoto.exe not found in dist.
 goto :failed
)

set "AFC_DIR="
if defined HUSH_AFC_TOOLS set "AFC_DIR=%HUSH_AFC_TOOLS%"
if not defined AFC_DIR if exist "native\afcclient.exe" set "AFC_DIR=%CD%\native"
if defined AFC_DIR (
 if exist "%AFC_DIR%\afcclient.exe" (
  if not exist "dist\HushPhoto\native" mkdir "dist\HushPhoto\native"
  copy /y "%AFC_DIR%\*.exe" "dist\HushPhoto\native\" >nul
  if exist "%AFC_DIR%\*.dll" copy /y "%AFC_DIR%\*.dll" "dist\HushPhoto\native\" >nul
  echo AFC tools bundled from "%AFC_DIR%".
 ) else (
  echo WARNING: AFC tools directory is missing afcclient.exe.
 )
) else (
 echo WARNING: AFC tools not supplied. USB transfer needs native tools.
)
copy /y README.md "dist\HushPhoto\README.md" >nul

echo.
echo [5/5] Packaging ZIP (this can be slower with large DLLs)...
powershell -NoProfile -Command "$ErrorActionPreference='Stop'; Compress-Archive -Path 'dist\HushPhoto\*' -DestinationPath 'dist\HushPhoto-Windows-Portable.zip' -CompressionLevel Fastest -Force"
if errorlevel 1 goto :failed

echo.
echo SUCCESS: dist\HushPhoto\HushPhoto.exe
echo ZIP: dist\HushPhoto-Windows-Portable.zip
exit /b 0

:failed
echo.
echo FAILED: Build stopped at the step displayed above.
exit /b 1
