@echo off
setlocal EnableDelayedExpansion
rem run_gui.bat - Windows app launcher

cd /d "%~dp0"

rem --------------------------------------------------
rem Launch Application
rem --------------------------------------------------
if not exist ".venv" (
    echo Virtual environment not found! Running setup_env.bat first...
    call setup_env.bat
)

call .venv\Scripts\activate.bat
python pytotext_gui.py
