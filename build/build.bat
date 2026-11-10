@echo off
REM ============================================================
REM  NTH — Build the Windows executable (one-file)
REM  Requires: Python 3.10+ on PATH
REM ============================================================
cd /d "%~dp0.."

echo [1/3] Installing dependencies...
python -m pip install -r requirements.txt pyinstaller || goto :fail

echo [2/3] Cleaning previous build...
if exist build\output rmdir /s /q build\output
if exist dist rmdir /s /q dist

echo [3/3] Running PyInstaller...
python -m PyInstaller build\NTH.spec --noconfirm --distpath dist || goto :fail

echo.
echo ============================================================
echo  SUCCESS: dist\NTH.exe
echo  First launch may take a few seconds (one-file unpack).
echo ============================================================
goto :eof

:fail
echo BUILD FAILED — see the output above.
exit /b 1
