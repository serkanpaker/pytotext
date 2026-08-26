#!/bin/bash
# setup_env.command - macOS / Linux environment setup script

# Get directory of this script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "=========================================="
echo " PyToText Virtual Environment Setup"
echo "=========================================="
echo ""

# Find python3
if command -v python3 &>/dev/null; then
    PYTHON_BIN="python3"
elif command -v python &>/dev/null; then
    PYTHON_BIN="python"
else
    echo "Error: Python 3 could not be found. Please install Python 3."
    read -p "Press Enter to exit..."
    exit 1
fi

echo "Using Python binary: $($PYTHON_BIN --version)"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment in .venv..."
    $PYTHON_BIN -m venv .venv
    if [ $? -ne 0 ]; then
        echo "Failed to create virtual environment."
        read -p "Press Enter to exit..."
        exit 1
    fi
else
    echo "Virtual environment .venv already exists."
fi

# Activate environment and install dependencies
echo "Activating virtual environment..."
source .venv/bin/activate

echo "Upgrading pip and installing requirements..."
pip install --upgrade pip
pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "Verifying application assets..."
    python3 -c "import pytotext_assets; pytotext_assets.ensure_logo_file()" 2>/dev/null
    echo ""
    echo "=========================================="
    echo " Setup completed successfully!"
    echo " You can now run the app using run_gui.command"
    echo "=========================================="
else
    echo "Error installing packages."
fi

read -p "Press Enter to finish..."
