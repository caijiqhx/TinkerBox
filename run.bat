@echo off
setlocal

cd /d "%~dp0"

echo.
echo   ==========================================
echo    ToolBox
echo   ==========================================
echo.

set "PYEXE="
where python >nul 2>nul
if not errorlevel 1 set "PYEXE=python"
if not defined PYEXE (
    where py >nul 2>nul
    if not errorlevel 1 set "PYEXE=py"
)

if not defined PYEXE goto :nopython

echo   Python : %PYEXE%
call %PYEXE% --version
echo   Folder : %CD%
echo.

set PYTHONUNBUFFERED=1

rem --detach: the real server runs in a detached process, so closing this
rem console window will NOT stop it. This is what makes "keep alive" work.
call %PYEXE% src\main.py --detach %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" goto :failed

echo   ------------------------------------------
echo   Done. You can close this window now.
echo   ------------------------------------------
if "%~1"=="" timeout /t 3 >nul 2>nul
exit /b 0

:failed
echo.
echo   ------------------------------------------
echo   Startup FAILED (code %RC%). Read the message above.
echo   ------------------------------------------
if "%~1"=="" pause
exit /b %RC%

:nopython
echo   [ERROR] Python 3 was not found on PATH.
echo   Install Python 3 first, then run this file again.
if "%~1"=="" pause
exit /b 1
