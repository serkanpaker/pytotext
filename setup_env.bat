@echo off
rem setup_env.bat - Windows environment setup script

cd /d "%~dp0"

echo ==========================================
echo  PyToText Virtual Environment Setup
echo ==========================================
echo.

where py >nul 2>nul
if %errorlevel% equ 0 (
    set PYTHON_CMD=py -3
) else (
    where python >nul 2>nul
    if %errorlevel% equ 0 (
        set PYTHON_CMD=python
    ) else (
        echo Error: Python was not found in PATH. Please install Python 3.
        pause
        exit /b 1
    )
)

echo Using Python command: %PYTHON_CMD%

if not exist ".venv" (
    echo Creating virtual environment in .venv...
    %PYTHON_CMD% -m venv .venv
    if %errorlevel% neq 0 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo Virtual environment .venv already exists.
)

echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo Upgrading pip and installing requirements...
python -m pip install --upgrade pip
pip install -r requirements.txt

if %errorlevel% equ 0 (
    echo Verifying application assets...
    python -c "import pytotext_assets; pytotext_assets.ensure_logo_file()" 2>nul
    echo.
    echo ==========================================
    echo  Setup completed successfully!
    echo  You can now run the app using run_gui.bat
    echo ==========================================
) else (
    echo Error installing packages.
)

pause
