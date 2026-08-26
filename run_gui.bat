@echo off
setlocal EnableDelayedExpansion
rem run_gui.bat - Windows app launcher

cd /d "%~dp0"

rem --------------------------------------------------
rem Auto-Update Check (silent if offline or not a git repo)
rem --------------------------------------------------
where git >nul 2>nul
if %ERRORLEVEL% equ 0 (
    if exist ".git" (
        git ls-remote --exit-code origin HEAD >nul 2>nul
        if %ERRORLEVEL% equ 0 (
            for /f "tokens=*" %%a in ('git rev-parse HEAD 2^>nul') do set LOCAL=%%a
            for /f "tokens=1" %%b in ('git ls-remote origin HEAD 2^>nul') do set REMOTE=%%b
            if defined REMOTE (
                if not "!LOCAL!"=="!REMOTE!" (
                    echo [PyToText] Update available! Pulling latest changes...
                    git pull origin main --ff-only 2>nul || git pull origin master --ff-only 2>nul
                    echo [PyToText] Updated successfully.
                )
            )
        )
    )
)

rem --------------------------------------------------
rem Launch Application
rem --------------------------------------------------
if not exist ".venv" (
    echo Virtual environment not found! Running setup_env.bat first...
    call setup_env.bat
)

call .venv\Scripts\activate.bat
python pytotext_gui.py
