# PyToText

**PyToText** is a powerful Python codebase and document merger designed for feeding structured code and project files to Large Language Models (LLMs) like Claude, ChatGPT, Gemini, DeepSeek, and local models.

It comes in two flavors:
1. **Modern Desktop GUI** (`pytotext_gui.py`): A responsive PyQt6 application featuring Dark/Light themes, cell-level inspection for Jupyter Notebooks (`.ipynb`) and partitioned Python/Markdown files, live previews, column sorting, search/filter, and versatile multi-part chunking.
2. **Interactive CLI** (`pytotext2.py`): A terminal-based shell for quickly navigating, selecting, filtering, and splitting files without a GUI.

---

## 🌟 Key Features

- **Multi-Format Ingestion**: Supports Python (`.py`), Jupyter Notebooks (`.ipynb`), Markdown (`.md`), Plain Text (`.txt`), YAML/JSON config files, CSV, HTML, and more.
- **Smart Cell Extraction**: Automatically detects notebook cells (`.ipynb`) and notebook-like comment cells (`# %%`, `# %% [markdown]`, `Cell 1`, `cEll1`, etc.) in `.py` and `.md` files. You can select, filter, or export specific cell ranges.
- **LLM Context Splitting Modes**:
  - **Single Merged File**: Concatenate all selected files into one document.
  - **Max Chars / Part**: Split merged content so no single output file exceeds your character limit (e.g. 100,000 chars).
  - **Max Tokens / Part**: Estimate token bounds for LLM context windows (e.g., 25k, 50k, 100k, 200k tokens).
  - **Fixed N Parts**: Evenly split the merged content across $N$ files.
- **Multi-Format Export**: Save merged outputs directly as `.txt`, `.py`, `.md`, or any custom file extension.
- **Interactive File Explorer**:
  - Filter by file category (Code, Docs, Notebooks, or All).
  - Search files by name in real time.
  - Multi-column sortable table (File Name, Extension, Size, Cell Count, Selection Status).
  - Relative / Absolute path toggling and file tree navigation.
- **Live Output & Preview**:
  - Built-in multi-part preview tab with real-time character/word/line/token counters.
  - Copy directly to clipboard with a single click.
  - Export individual parts or batch-export all parts to a chosen folder.
- **Modern UI / UX**:
  - Theme support (Dark, Light, and System modes).
  - Responsive layout (fits split-screen / half-screen tiling on macOS and Windows).
  - Embedded self-contained assets in `pytotext_assets.py` (no missing icons or external image dependencies).

---

## 📁 Project Structure

```text
Pytotext/
├── pytotext_gui.py        # PyQt6 Desktop GUI application
├── pytotext2.py           # Core processing engine & interactive CLI
├── pytotext_assets.py     # Embedded vector icons, logos, UI assets
├── requirements.txt       # Python package dependencies (PyQt6)
├── setup_env.command      # macOS/Linux automated environment setup
├── run_gui.command        # macOS/Linux launcher
├── setup_env.bat          # Windows automated virtual environment setup
├── run_gui.bat            # Windows launcher
└── README.md              # Project documentation
```

---

## 📋 Prerequisites

- **Python 3.9+** (Python 3.10, 3.11, or 3.12 recommended)
- **pip** package manager

---

## 🚀 Quick Start & Installation

### Option 1: Automated Script Setup (Recommended)

#### macOS / Linux
1. Open Terminal and navigate to the project directory.
2. Make scripts executable (only needed once):
   ```bash
   chmod +x setup_env.command run_gui.command
   ```
3. Run the setup script:
   ```bash
   ./setup_env.command
   ```
   *(Or double-click `setup_env.command` in macOS Finder)*.

#### Windows
1. Double-click `setup_env.bat` (or run `setup_env.bat` in Command Prompt / PowerShell).

---

### Option 2: Manual Installation

If you prefer to configure your environment manually:

1. **Create and activate a virtual environment:**
   - **macOS / Linux:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```
   - **Windows:**
     ```cmd
     python -m venv .venv
     .venv\Scripts\activate
     ```

2. **Install dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

---

## 🖥️ Running the Application

### 1. Graphical User Interface (GUI)

- **macOS / Linux:**
  - Double-click `run_gui.command`, or run:
    ```bash
    ./run_gui.command
    ```
- **Windows:**
  - Double-click `run_gui.bat`, or run:
    ```cmd
    run_gui.bat
    ```
- **Direct Python Launch:**
  ```bash
  python pytotext_gui.py
  ```

---

### 2. Command Line Interface (CLI)

PyToText also includes an interactive terminal shell:

```bash
python pytotext2.py
```

#### Common CLI Commands:
- `ls`: List files in the current folder.
- `cd <folder>` / `back`: Navigate directories.
- `add <file>` / `addall`: Select files for export.
- `remove <file>` / `clear`: Deselect files.
- `nbinfo <file>`: Inspect cell structure of a notebook or cell-based script.
- `cells <file> 1,3,5`: Select specific cells from a file.
- `export`: Generate merged output files.
- `help`: Display all available terminal commands.

---

## 📖 How to Use the GUI

1. **Open a Project Folder**:
   - Click **"Open Folder"** or press `Ctrl+O` / `Cmd+O` to select the root folder of your project.
2. **Select Files**:
   - Check the boxes next to the files you want to include in the output.
   - Use **"Select All"** (`Ctrl+Alt+A`), **"Deselect All"** (`Ctrl+D`), or filter by file types (*Code*, *Docs*, *Notebooks*).
   - Click any column header (Name, Ext, Size, Cells) to sort your files.
3. **Configure Cell Selections (Optional)**:
   - For `.ipynb` or cell-partitioned `.py`/`.md` files, click the cell count or choose specific cell ranges to omit unwanted outputs or exploratory scratchpads.
4. **Choose Split Mode**:
   - **Single File**: Combines everything into one file.
   - **Max Chars / Part**: Splits content at your chosen character ceiling (e.g., 100,000 characters).
   - **Max Tokens / Part**: Splits content based on token estimates for LLM context limits.
   - **Fixed N Parts**: Splits content evenly into $N$ files.
5. **Preview & Export**:
   - Click **"Generate & Preview"** (`Ctrl+G`) to inspect the merged parts in the live viewer.
   - Click **"Copy Part"** (`Ctrl+Shift+C`) to paste directly into your LLM chat window, or click **"Save Part / Save All Parts"** (`Ctrl+S` / `Ctrl+E`) to save to disk in `.txt`, `.py`, `.md`, or your preferred format.

---

## 🛠️ Keyboard Shortcuts (GUI)

| Shortcut | Action |
| :--- | :--- |
| `Ctrl+O` / `Cmd+O` | Open Folder |
| `Ctrl+R` / `Cmd+R` | Refresh / Rescan File Tree |
| `Ctrl+Alt+A` / `Cmd+Alt+A` | Select All Files |
| `Ctrl+D` / `Cmd+D` | Deselect All Files |
| `Ctrl+F` / `Cmd+F` | Focus Search Bar / Toggle Find |
| `Ctrl+G` / `Cmd+G` | Generate & Preview Merged Text |
| `Ctrl+Shift+S` / `Cmd+Shift+S` | Split Merged Text into Parts |
| `Ctrl+Shift+C` / `Cmd+Shift+C` | Copy Active Part or Viewer to Clipboard |
| `Ctrl+S` / `Cmd+S` | Save Active Part or Merged File |
| `Ctrl+E` / `Cmd+E` | Export All Generated Output Files |
| `Ctrl+T` / `Cmd+T` | Toggle Dark / Light / System Theme |

---

## 📄 License

This project is open-source and free to use for personal and commercial development workflows.
