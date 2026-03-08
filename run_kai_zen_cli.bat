@echo off
setlocal
if not defined COLORTERM set COLORTERM=truecolor
pushd "%~dp0"
python "%~dp0kai_zen_tui.py" %*
set EXITCODE=%ERRORLEVEL%
popd
exit /b %EXITCODE%
