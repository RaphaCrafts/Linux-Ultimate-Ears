@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1
where pyw >nul 2>nul
if errorlevel 1 goto use_python
start "" pyw -3 "%~dp0scripts\windows_launcher.py" %*
goto finished
:use_python
where pythonw >nul 2>nul
if errorlevel 1 goto missing_python
start "" pythonw "%~dp0scripts\windows_launcher.py" %*
goto finished
:missing_python
echo Install Python 3.11 through 3.14 from https://www.python.org/downloads/windows/
echo Enable the Python launcher or Add Python to PATH, then open this file again.
pause
popd
exit /b 1
:finished
popd
exit /b 0
