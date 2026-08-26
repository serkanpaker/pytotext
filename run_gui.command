#!/bin/bash
# run_gui.command - macOS / Linux app launcher

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# --------------------------------------------------
# Launch Application
# --------------------------------------------------
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found! Running setup_env.command first..."
    bash setup_env.command
fi

source .venv/bin/activate
python3 pytotext_gui.py
