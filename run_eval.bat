@echo off
setlocal
cd /d "%~dp0" || exit /b 2
set "PYEXE="
if exist "python\python.exe" set "PYEXE=python\python.exe"
if defined PYEXE goto check
where py >nul 2>nul && set "PYEXE=py -3"
if defined PYEXE goto check
where python >nul 2>nul && set "PYEXE=python"
if defined PYEXE goto check
goto missing
:check
%PYEXE% -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 3)" >nul 2>nul
if errorlevel 1 goto old
%PYEXE% -X utf8 -m evm.evalrun --golden "eval/golden_card.json" %*
set RC=%ERRORLEVEL%
goto done
:old
echo Python 3.12 or newer is required (an older one was found). See the manual (README).
set RC=2
goto done
:missing
echo Python 3.12 or newer is required. See the manual (README).
set RC=2
:done
if "%EVM_NO_PAUSE%"=="1" exit /b %RC%
if not "%RC%"=="0" pause
exit /b %RC%
