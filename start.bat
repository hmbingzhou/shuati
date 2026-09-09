@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 set PYEXE=py
if not defined PYEXE set PYEXE=python
%PYEXE% launcher.py
pause
