#!/bin/bash
# run_gui.command - macOS / Linux app launcher

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# --------------------------------------------------
# Auto-Update Check (silent if offline or not a git repo)
# --------------------------------------------------
if command -v git &>/dev/null && [ -d ".git" ]; then
    if git ls-remote --exit-code origin HEAD &>/dev/null 2>&1; then
        LOCAL=$(git rev-parse HEAD 2>/dev/null)
        REMOTE=$(git ls-remote origin HEAD 2>/dev/null | awk '{print $1}')
        if [ -n "$REMOTE" ] && [ "$LOCAL" != "$REMOTE" ]; then
            echo "[PyToText] Update available! Pulling latest changes..."
            git pull origin main --ff-only 2>/dev/null || git pull origin master --ff-only 2>/dev/null
            echo "[PyToText] Updated successfully."
        fi
    fi
fi

# --------------------------------------------------
# Launch Application
# --------------------------------------------------
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found! Running setup_env.command first..."
    bash setup_env.command
fi

source .venv/bin/activate
python3 pytotext_gui.py
