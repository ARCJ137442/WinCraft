@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0\..\.."
python examples\integrations\obsidian_workspace\configure.py
if errorlevel 1 pause
