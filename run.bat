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

echo   Python   : %PYEXE%
call %PYEXE% --version
echo   Folder   : %CD%
echo   Starting : src\main.py %*
echo.
echo   ------------------------------------------
echo.

set PYTHONUNBUFFERED=1

call %PYEXE% src\main.py %*
set "RC=%ERRORLEVEL%"

echo.
echo   ------------------------------------------
echo   ToolBox exited (code %RC%).
goto :end

:nopython
echo   [ERROR] Python 3 was not found on PATH.
echo   Install Python 3 first, then run this file again.
set "RC=1"

:end
echo.
rem Pause only when double-clicked (no arguments) AND something failed,
rem so the window stays open long enough to read the error.
if not "%RC%"=="0" if "%~1"=="" pause
exit /b %RC%
