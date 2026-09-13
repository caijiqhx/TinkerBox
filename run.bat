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
rem console window will NOT stop it. That is what makes "keep alive" work.
rem No browser window is opened by default -- open the printed address
rem yourself (bookmark it), or pass --open to launch a window here.
call %PYEXE% src\main.py --detach %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" goto :failed

echo   ------------------------------------------
echo   Service is running in the background.
echo   Open the address shown above in your browser
echo   (bookmark it). This window closes by itself.
echo   ------------------------------------------
if "%~1"=="" timeout /t 5 >nul 2>nul
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
