@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1
where py >nul 2>nul
if errorlevel 1 goto use_python
py -3 scripts\windows_launcher.py %*
goto finished
:use_python
where python >nul 2>nul
if errorlevel 1 goto missing_python
python scripts\windows_launcher.py %*
goto finished
:missing_python
echo Install Python 3.11 or newer from https://www.python.org/downloads/windows/
echo Enable the Python launcher or Add Python to PATH, then open this file again.
pause
popd
exit /b 1
:finished
set "launch_result=%errorlevel%"
if not "%launch_result%"=="0" pause
popd
exit /b %launch_result%
