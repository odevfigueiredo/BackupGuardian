@echo off
setlocal
pushd "%~dp0" || exit /b 1

py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto use_launcher

python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto use_python

echo Python 3.10 ou superior nao encontrado. Instale o Python e tente novamente.
set "result=1"
goto finish

:use_launcher
py -3 guardian_gui.py
set "result=%errorlevel%"
goto finish

:use_python
python guardian_gui.py
set "result=%errorlevel%"

:finish
popd
if not "%result%"=="0" pause
exit /b %result%
