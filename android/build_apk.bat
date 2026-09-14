@echo off
REM Build Android APK (Windows wrapper).
REM Scripts are blocked by default execution policy, so use Bypass here.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_apk.ps1" %*
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo.
  echo Build failed with exit code %EXITCODE%. See the messages above.
)
pause
exit /b %EXITCODE%
