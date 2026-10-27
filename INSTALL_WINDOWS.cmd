@echo off
setlocal
cd /d "%~dp0"
echo ============================================
echo   Medical Daily Checklist - Windows install
echo ============================================
echo.
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "%~dp0install_windows.py"
    goto result
)
where python >nul 2>nul
if %errorlevel%==0 (
    python "%~dp0install_windows.py"
    goto result
)
echo Python was not found.
echo Install Python 3 from python.org with Tcl/Tk support,
echo then run this installer again.
set "RESULT=1"
goto finished
:result
set "RESULT=%errorlevel%"
:finished
echo.
if not "%RESULT%"=="0" echo Installation did not finish successfully.
pause
exit /b %RESULT%
