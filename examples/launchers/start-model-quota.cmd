@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0\..\.."
python examples\integrations\model_quota\configure_model_quota.py
if errorlevel 1 pause
