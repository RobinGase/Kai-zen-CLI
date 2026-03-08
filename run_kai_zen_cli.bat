@echo off
setlocal
pushd "%~dp0"
python "%~dp0kai_zen_tui.py" %*
set EXITCODE=%ERRORLEVEL%
popd
exit /b %EXITCODE%
