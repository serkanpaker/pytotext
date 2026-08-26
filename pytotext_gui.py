#!/usr/bin/env python3
"""
pytotext_gui.py

PyQt6 User Interface for PyToText (v2 - Professional Desktop Edition).
Refined per user request:
- Cell Logic: Removed redundant '[Cell 1 | markdown]' title prefix. Clean pure cell splitting & rendering.
- Presets: Removed unnecessary presets menu from header bar.
- Mode Options: Added 'Max Tokens / Part' in addition to 'Max Chars / Part' and 'Fixed N Parts'.
- Window Dimensions: Reduced minimum window width & height (min: 680x480) so it easily fits on half-screen tiled layouts (macOS split-screen / snapping).
- Aesthetics & Styling: Symmetrical card geometry, softer modern rounded corners (8px radii), harmonious colors,
  improved contrast, refined buttons, balanced spacing, and elegant subtle borders.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    from PyQt6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QThread, QTimer, pyqtSignal
    from PyQt6.QtGui import (
        QAction,
        QColor,
        QFont,
        QIcon,
        QKeySequence,
        QPainter,
        QPalette,
        QPen,
        QTextBlockFormat,
        QTextCursor,
        QTextDocument,
        QTextFormat,
    )
    from PyQt6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QFileDialog,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QRadioButton,
        QScrollArea,
        QSizePolicy,
        QSpinBox,
        QSplitter,
        QSplitterHandle,
        QStackedWidget,
        QStyle,
        QTabWidget,
        QTableWidget,
        QTableWidgetItem,
        QTextEdit,
        QToolButton,
        QTreeWidget,
        QTreeWidgetItem,
        QTreeWidgetItemIterator,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    print("PyQt6 is required. Please run setup_env.command (macOS) or setup_env.bat (Windows).")
    sys.exit(1)

# Import core logic and assets
SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import pytotext2
import pytotext_assets

CONFIG_FILE = SCRIPT_DIR / "pytotext_config.json"


# --------------------------------------------------
# Extensions & Pure Cell Parsers
# --------------------------------------------------
def is_md_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in {".md", ".markdown"}


def is_supported_gui_file(path: Path) -> bool:
    return pytotext2.is_supported_file(path)


UNIFIED_CELL_MARKER_RE = re.compile(
    r"""
    ^
    \s*
    (?:
        \#\s*%%(?:\s*\[[^\]]+\])?      # # %% or # %% [code] or # %% [markdown]
        |
        \#\s*cell\b.*$                 # # Cell 1 / # Cell / # cell1: / # Cell 0: TUM IMPORTS / # Cell 0
        |
        <!--\s*cell(?:\s+\d+)?\s*-->   # <!-- cell --> or <!-- cell 1 -->
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

CELL_NUM_EXTRACT_RE = re.compile(r"#\s*cell\s*(\d+[a-z]?)\b", re.IGNORECASE)

# Fenced code block markers (```python / ```)
FENCED_CODE_OPEN_RE = re.compile(r"^\s*```(?:python|py|python3)?\s*$", re.IGNORECASE)
FENCED_CODE_CLOSE_RE = re.compile(r"^\s*```\s*$")


def has_jupyter_markers(text: str) -> bool:
    """Return True if text contains any Jupyter-like cell markers."""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if UNIFIED_CELL_MARKER_RE.match(stripped):
            return True
        if FENCED_CODE_OPEN_RE.match(stripped):
            return True
    return False


def parse_fenced_code_cells(text: str) -> List[dict]:
    """Parse text containing ```python / ``` fenced blocks into cell dicts."""
    lines = text.splitlines(keepends=True)
    cells: List[dict] = []
    current_lines: List[str] = []
    in_fence = False
    fence_lines: List[str] = []
    fence_open_line = "```python\n"
    inter_fence_spacing = ""
    cell_idx = 0

    for line in lines:
        stripped = line.strip()
        if not in_fence and FENCED_CODE_OPEN_RE.match(stripped):
            # Flush any accumulated non-fence text as a markdown cell
            if current_lines:
                content = "".join(current_lines)
                if content.strip():
                    cell_idx += 1
                    cells.append({
                        "cell_type": "markdown",
                        "source": content,
                        "cell_label": str(cell_idx),
                        "hidden_prefix": "",
                        "hidden_suffix": "",
                        "is_fenced": False,
                    })
                    inter_fence_spacing = ""
                else:
                    # Whitespace / blank lines between fences
                    inter_fence_spacing = content
                current_lines = []
            in_fence = True
            fence_open_line = (inter_fence_spacing + line) if line.endswith("\n") else (inter_fence_spacing + line + "\n")
            inter_fence_spacing = ""
            fence_lines = []
        elif in_fence and FENCED_CODE_CLOSE_RE.match(stripped):
            # End of fenced block → code cell
            cell_idx += 1
            fence_close_line = line if line.endswith("\n") else line + "\n"
            explicit_label = None
            for f_line in fence_lines:
                match = CELL_NUM_EXTRACT_RE.search(f_line)
                if match:
                    explicit_label = match.group(1)
                    break

            cells.append({
                "cell_type": "code",
                "source": "".join(fence_lines),
                "cell_label": explicit_label or str(cell_idx),
                "hidden_prefix": fence_open_line,
                "hidden_suffix": fence_close_line,
                "is_fenced": True,
            })
            in_fence = False
            fence_lines = []
        elif in_fence:
            fence_lines.append(line)
        else:
            current_lines.append(line)

    # Flush remaining
    if in_fence and fence_lines:
        cell_idx += 1
        explicit_label = None
        for f_line in fence_lines:
            match = CELL_NUM_EXTRACT_RE.search(f_line)
            if match:
                explicit_label = match.group(1)
                break

        cells.append({
            "cell_type": "code",
            "source": "".join(fence_lines),
            "cell_label": explicit_label or str(cell_idx),
            "hidden_prefix": fence_open_line,
            "hidden_suffix": "```\n",
            "is_fenced": True,
        })
    if current_lines:
        content = "".join(current_lines)
        if content.strip():
            cell_idx += 1
            cells.append({
                "cell_type": "markdown",
                "source": content,
                "cell_label": str(cell_idx),
                "hidden_prefix": "",
                "hidden_suffix": "",
                "is_fenced": False,
            })

    return cells


BANNER_LINE_RE = re.compile(r"^\s*#\s*[=\-_*~]{3,}\s*$")


def is_unified_cell_marker_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return bool(UNIFIED_CELL_MARKER_RE.match(stripped))


def is_cell_or_banner_marker_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return is_unified_cell_marker_line(line) or bool(BANNER_LINE_RE.match(stripped)) or bool(FENCED_CODE_OPEN_RE.match(stripped))


def extract_unified_cell_label(header_line: str) -> Optional[str]:
    match = CELL_NUM_EXTRACT_RE.search(header_line)
    if match:
        return pytotext2.normalize_cell_label(match.group(1))
    return None


def parse_unified_cells(text: str, is_markdown: bool = False) -> List[dict]:
    lines = text.splitlines(keepends=True)
    if not lines:
        return []

    clusters: List[Tuple[int, int]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        is_candidate = is_cell_or_banner_marker_line(line)
        if is_markdown and not is_candidate:
            stripped = line.strip()
            if stripped.startswith("# ") or stripped.startswith("## "):
                is_candidate = True

        if is_candidate:
            start_m = i
            has_cell_marker = is_unified_cell_marker_line(line)
            while i + 1 < len(lines) and is_cell_or_banner_marker_line(lines[i + 1]):
                if is_unified_cell_marker_line(lines[i + 1]):
                    has_cell_marker = True
                i += 1
            if has_cell_marker:
                clusters.append((start_m, i + 1))
        i += 1

    if not clusters:
        return [{
            "cell_type": "markdown" if is_markdown else "code",
            "source": text,
            "synthetic_single_cell": True,
            "from_markers": False,
            "cell_label": "1" if is_markdown else None,
            "hidden_prefix": "",
            "hidden_suffix": "",
        }]

    cells: List[dict] = []
    first_cluster_start = clusters[0][0]
    if first_cluster_start > 0:
        preamble = "".join(lines[:first_cluster_start])
        if preamble.strip():
            cells.append({
                "cell_type": "markdown" if is_markdown else "code",
                "source": preamble,
                "synthetic_single_cell": False,
                "from_markers": True,
                "cell_label": "0",
                "hidden_prefix": "",
                "hidden_suffix": "",
            })

    for idx, (m_start, m_end) in enumerate(clusters):
        next_start = clusters[idx + 1][0] if idx + 1 < len(clusters) else len(lines)
        chunk = "".join(lines[m_start:next_start])

        explicit_label = None
        for m_idx in range(m_start, m_end):
            lbl = extract_unified_cell_label(lines[m_idx])
            if lbl is not None:
                explicit_label = lbl
                break

        cell_type = "markdown" if is_markdown else "code"
        for m_idx in range(m_start, m_end):
            m_line_lower = lines[m_idx].lower()
            if "[markdown]" in m_line_lower or "[md]" in m_line_lower:
                cell_type = "markdown"
                break

        # Separate hidden markers (# %%, <!-- cell -->, ```python) from visible header lines (e.g. # Cell)
        cluster_lines = lines[m_start:m_end]
        hidden_prefix_lines = []
        visible_header_lines = []
        for cline in cluster_lines:
            cstripped = cline.strip()
            if cstripped.startswith("# %%") or cstripped.startswith("<!-- cell") or FENCED_CODE_OPEN_RE.match(cstripped):
                hidden_prefix_lines.append(cline)
            else:
                visible_header_lines.append(cline)

        body_lines = lines[m_end:next_start]
        hidden_suffix_lines = []
        clean_body_lines = []
        for bline in body_lines:
            if FENCED_CODE_CLOSE_RE.match(bline.strip()):
                hidden_suffix_lines.append(bline)
            else:
                clean_body_lines.append(bline)

        visible_source = "".join(visible_header_lines + clean_body_lines)
        hidden_prefix = "".join(hidden_prefix_lines)
        hidden_suffix = "".join(hidden_suffix_lines)

        cells.append({
            "cell_type": cell_type,
            "source": visible_source,
            "synthetic_single_cell": False,
            "from_markers": True,
            "cell_label": explicit_label or str(idx + 1),
            "hidden_prefix": hidden_prefix,
            "hidden_suffix": hidden_suffix,
        })

    return cells


def parse_md_cells(path_or_text: Path | str) -> List[dict]:
    if isinstance(path_or_text, Path):
        text = pytotext2.read_text_best_effort(path_or_text)
    else:
        text = str(path_or_text)
    return parse_unified_cells(text, is_markdown=True)


def parse_py_cells_unified(path_or_text: Path | str) -> List[dict]:
    if isinstance(path_or_text, Path):
        text = pytotext2.read_text_best_effort(path_or_text)
    else:
        text = str(path_or_text)
    return parse_unified_cells(text, is_markdown=False)


def render_md_with_cells(
    path_or_text: Path | str,
    selected_cells: Optional[List[str]],
    display_name: Optional[str] = None,
    cell_format: str = pytotext2.CELL_FORMAT_DIVIDER,
) -> str:
    """Render markdown cells cleanly without unnecessary '[Cell X | markdown]' titles."""
    cells = parse_md_cells(path_or_text)
    wanted_norm = None if selected_cells is None else {pytotext2.normalize_cell_label(x) for x in selected_cells}

    lines = []
    if display_name:
        lines.append(f"# ==========================================\n# File: {display_name}\n# ==========================================\n")

    for seq, cell in enumerate(cells, start=1):
        cell_label = str(cell.get("cell_label", seq))
        if wanted_norm is not None and pytotext2.normalize_cell_label(cell_label) not in wanted_norm:
            continue

        text = str(cell.get("source", ""))
        pytotext2.append_plain_text(lines, text)

    return "\n".join(lines).rstrip() + "\n"


def render_py_with_unified_cells(
    path: Path,
    selected_cells: Optional[List[str]],
    display_name: Optional[str] = None,
    cell_format: str = pytotext2.CELL_FORMAT_DIVIDER,
) -> str:
    """Render python cells cleanly without unnecessary '[Cell X | code]' titles."""
    cells = parse_py_cells_unified(path)
    wanted_norm = None if selected_cells is None else {pytotext2.normalize_cell_label(x) for x in selected_cells}

    header = f"# ==========================================\n# File: {display_name}\n# ==========================================\n\n"
    lines = [header]

    for seq, cell in enumerate(cells, start=1):
        cell_label = str(cell.get("cell_label") or seq)
        if wanted_norm is not None and pytotext2.normalize_cell_label(cell_label) not in wanted_norm:
            continue

        text = str(cell.get("source", ""))
        pytotext2.append_plain_text(lines, text)

    return "\n".join(lines).rstrip() + "\n"


def render_generic_text_file(path: Path, display_name: str) -> str:
    content = pytotext2.read_text_best_effort(path)
    header = f"# ==========================================\n# File: {display_name}\n# ==========================================\n\n"
    return header + content.rstrip() + "\n\n"


def generate_folder_tree(root: Path, file_paths: List[Path], max_items: int = 5000) -> str:
    if not file_paths:
        return f"{root.name}/ (Empty)\n"

    rel_paths = sorted([pytotext2.safe_relpath(p, root) for p in file_paths])
    truncated = False
    if len(rel_paths) > max_items:
        rel_paths = rel_paths[:max_items]
        truncated = True

    tree_dict: dict = {}
    for rel in rel_paths:
        parts = rel.split("/")
        curr = tree_dict
        for part in parts:
            curr = curr.setdefault(part, {})

    lines: List[str] = [f"{root.name}/"]

    def _build_lines(node: dict, prefix: str = ""):
        keys = list(node.keys())
        for idx, key in enumerate(keys):
            is_last = idx == len(keys) - 1
            branch = "└── " if is_last else "├── "
            child_prefix = "    " if is_last else "│   "
            children = node[key]
            lines.append(f"{prefix}{branch}{key}")
            if children:
                _build_lines(children, prefix + child_prefix)

    _build_lines(tree_dict)

    if truncated:
        lines.append(f"\n... [Tree truncated: showing first {max_items:,} items out of {len(file_paths):,}]")

    return "\n".join(lines)


# --------------------------------------------------
# Balanced Smart Text Splitting Algorithm
# --------------------------------------------------
def parse_coefficient_split_targets(
    coefficients_str: str,
    total_chars: int,
    base_part_count: int,
    mode: str,
    max_chars: int,
) -> List[int]:
    cleaned = coefficients_str.replace(":", ",").replace("x", "").strip()
    tokens = [t.strip() for t in cleaned.split(",") if t.strip()]

    coeffs: List[float] = []
    for t in tokens:
        try:
            val = float(t)
            if val > 0:
                coeffs.append(val)
        except ValueError:
            continue

    if mode == "fixedparts":
        num_parts = max(1, base_part_count)
        if not coeffs:
            coeffs = [1.0] * num_parts
        elif len(coeffs) < num_parts:
            coeffs = coeffs + [1.0] * (num_parts - len(coeffs))
        elif len(coeffs) > num_parts:
            coeffs = coeffs[:num_parts]

        sum_c = sum(coeffs)
        targets = [max(1, int(round((c / sum_c) * total_chars))) for c in coeffs]
        return targets
    else:
        if coeffs and len(coeffs) > 1:
            sum_c = sum(coeffs)
            targets = [max(1, min(max_chars, int(round((c / sum_c) * total_chars)))) for c in coeffs]
            return targets

        num_parts = max(1, base_part_count)
        avg_target = (total_chars + num_parts - 1) // num_parts

        if not coeffs:
            targets = [min(max_chars, avg_target)] * num_parts
        else:
            scaled_target = max(1, min(max_chars, int(round(avg_target * coeffs[0]))))
            needed = max(1, (total_chars + scaled_target - 1) // scaled_target)
            targets = [scaled_target] * needed
        return targets


def split_text_balanced(
    text: str,
    mode: str,
    limit_value: int,
    num_parts: int,
    cell_format: str = "plain",
    coefficients_str: str = "",
    include_header: bool = True,
    prepend_ai_prompt: bool = True,
    ai_prompt_text: str = 'Just say "I understood". I will share the prompt later.',
    append_footer: bool = False,
    footer_text: str = '--- End of Part {part} of {total_parts} ---',
    cancel_check=None,
) -> List[str]:
    if not text.strip():
        return []

    lines = text.splitlines(keepends=True)
    total_chars = len(text)
    if total_chars == 0:
        return []

    # If mode is maxtokens, limit_value is tokens -> convert to char ceiling (~4 chars/token)
    if mode == "maxtokens":
        max_chars = limit_value * 4
        effective_mode = "maxchars"
    else:
        max_chars = limit_value
        effective_mode = mode

    if effective_mode == "maxchars":
        base_parts = max(1, (total_chars + max_chars - 1) // max_chars)
    else:
        base_parts = max(1, num_parts)

    target_sizes = parse_coefficient_split_targets(
        coefficients_str=coefficients_str,
        total_chars=total_chars,
        base_part_count=base_parts,
        mode=effective_mode,
        max_chars=max_chars,
    )
    total_target_parts = len(target_sizes)

    line_lengths = [len(l) for l in lines]
    remaining_total_chars = total_chars

    parts: List[str] = []
    current_chunk: List[str] = []
    current_len = 0
    current_part_idx = 0

    for i, line in enumerate(lines):
        if cancel_check and i % 2000 == 0 and cancel_check():
            return []

        line_len = line_lengths[i]
        remaining_parts_count = max(1, total_target_parts - len(parts))

        if coefficients_str.strip():
            target_limit = target_sizes[current_part_idx] if current_part_idx < len(target_sizes) else (
                max_chars if effective_mode == "maxchars" else target_sizes[-1]
            )
        else:
            dynamic_ideal = (remaining_total_chars + remaining_parts_count - 1) // remaining_parts_count
            target_limit = min(max_chars, dynamic_ideal) if effective_mode == "maxchars" else dynamic_ideal

        is_file_break = line.startswith("# File:") or line.startswith("# =====")
        is_cell_break = (
            is_file_break
            or line.startswith("# Cell")
            or is_unified_cell_marker_line(line)
            or line.startswith("# ---")
            or line.startswith("## ")
        )

        soft_threshold = int(target_limit * 0.985)
        hard_limit = min(target_limit, max_chars) if effective_mode == "maxchars" else target_limit

        should_roll = False
        if current_chunk:
            if effective_mode == "fixedparts":
                if len(parts) < total_target_parts - 1:
                    if is_cell_break and current_len >= soft_threshold:
                        should_roll = True
                    elif (current_len + line_len) > hard_limit:
                        should_roll = True
            else:
                if len(parts) < total_target_parts - 1:
                    if is_cell_break and current_len >= soft_threshold:
                        should_roll = True
                    elif (current_len + line_len) > hard_limit:
                        should_roll = True
                else:
                    if (current_len + line_len) > max_chars:
                        should_roll = True

        if should_roll:
            part_str = "".join(current_chunk)
            parts.append(part_str)
            remaining_total_chars -= len(part_str)
            current_chunk = []
            current_len = 0
            current_part_idx += 1

        current_chunk.append(line)
        current_len += line_len

    if current_chunk:
        parts.append("".join(current_chunk))

    total_parts = len(parts)
    formatted_parts: List[str] = []
    for idx, part_str in enumerate(parts, start=1):
        sections: List[str] = []

        if prepend_ai_prompt and ai_prompt_text.strip():
            formatted_ai = ai_prompt_text.format(part=idx, total_parts=total_parts, total=total_parts)
            sections.append(formatted_ai.strip() + "\n\n")

        if include_header:
            p_chars = len(part_str)
            p_tokens = p_chars // 4
            part_header = (
                f"# ==========================================\n"
                f"# Part {idx} of {total_parts} (Chars: {p_chars:,} | ~{p_tokens:,} tokens)\n"
                f"# ==========================================\n\n"
            )
            sections.append(part_header)

        sections.append(part_str)

        if append_footer and footer_text.strip():
            formatted_foot = footer_text.format(part=idx, total_parts=total_parts, total=total_parts)
            sections.append("\n\n" + formatted_foot.strip())

        formatted_parts.append("".join(sections))

    return formatted_parts


# --------------------------------------------------
# Background Worker Threads
# --------------------------------------------------
class FolderScanWorker(QThread):
    finished_signal = pyqtSignal(dict)
    progress_signal = pyqtSignal(int)
    error_signal = pyqtSignal(str)

    IGNORED_DIR_NAMES = {
        "venv", ".venv", "env", ".env", "__pycache__", "node_modules", ".git", ".hg", ".svn",
        "audit-snapshots", "dist", "build", ".pytest_cache", ".mypy_cache", ".cache", ".next",
        ".nuxt", "coverage", ".tox", ".idea", ".vscode", "vendor", "target", "bin", "obj",
        ".dataset", ".data", "datasets", "logs", "tmp", "temp", "site-packages"
    }

    def __init__(self, root: Path):
        super().__init__()
        self.root = root

    def run(self):
        try:
            discovered: Dict[str, Path] = {}
            count = 0
            for dirpath, dirnames, filenames in os.walk(self.root):
                dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in self.IGNORED_DIR_NAMES]
                for filename in filenames:
                    if filename.startswith("."):
                        continue
                    p = Path(dirpath) / filename
                    if is_supported_gui_file(p):
                        try:
                            rel = pytotext2.safe_relpath(p, self.root)
                            discovered[rel] = p
                            count += 1
                            if count % 200 == 0:
                                self.progress_signal.emit(count)
                        except ValueError:
                            continue

            sorted_discovered = {rel: discovered[rel] for rel in sorted(discovered.keys())}
            self.finished_signal.emit(sorted_discovered)
        except Exception as e:
            self.error_signal.emit(str(e))


class FolderCharCountWorker(QThread):
    finished_signal = pyqtSignal(dict, int, int)
    error_signal = pyqtSignal(str)

    def __init__(self, discovered_files: Dict[str, Path]):
        super().__init__()
        self.discovered_files = discovered_files

    def run(self):
        try:
            results: Dict[str, int] = {}
            total_chars = 0
            for rel_path, abs_path in self.discovered_files.items():
                content = pytotext2.read_text_best_effort(abs_path)
                length = len(content)
                results[rel_path] = length
                total_chars += length
            total_tokens = total_chars // 4
            self.finished_signal.emit(results, total_chars, total_tokens)
        except Exception as e:
            self.error_signal.emit(str(e))


class FolderMergeWorker(QThread):
    finished_signal = pyqtSignal(str, int)
    error_signal = pyqtSignal(str)

    def __init__(
        self,
        selected_files: List[str],
        discovered_files: Dict[str, Path],
        cell_map: Dict[str, Optional[List[str]]],
        cell_format: str,
    ):
        super().__init__()
        self.selected_files = selected_files
        self.discovered_files = discovered_files
        self.cell_map = cell_map
        self.cell_format = cell_format

    def run(self):
        try:
            rendered_chunks: List[str] = []
            for display in self.selected_files:
                path = self.discovered_files[display]
                if is_md_file(path):
                    rendered_chunks.append(render_md_with_cells(path, self.cell_map.get(display), display_name=display, cell_format=self.cell_format))
                elif pytotext2.is_py_file(path):
                    rendered_chunks.append(render_py_with_unified_cells(path, self.cell_map.get(display), display_name=display, cell_format=self.cell_format))
                elif pytotext2.is_notebook_file(path):
                    rendered_chunks.append(pytotext2.render_file_content(path, self.cell_map, display, cell_format=self.cell_format))
                else:
                    rendered_chunks.append(render_generic_text_file(path, display))

            merged = "\n".join(rendered_chunks)
            self.finished_signal.emit(merged, len(self.selected_files))
        except Exception as e:
            self.error_signal.emit(str(e))


class TextProcessWorker(QThread):
    finished_signal = pyqtSignal(list, str)
    cancelled_signal = pyqtSignal()
    error_signal = pyqtSignal(str)

    def __init__(
        self,
        mode: str,
        text_buffer: str,
        limit_value: int,
        num_parts: int,
        cell_format: str = "plain",
        coefficients_str: str = "",
        include_header: bool = True,
        prepend_ai_prompt: bool = True,
        ai_prompt_text: str = 'Just say "I understood". I will share the prompt later.',
        append_footer: bool = False,
        footer_text: str = '--- End of Part {part} of {total_parts} ---',
    ):
        super().__init__()
        self.mode = mode
        self.text_buffer = text_buffer
        self.limit_value = limit_value
        self.num_parts = num_parts
        self.cell_format = cell_format
        self.coefficients_str = coefficients_str
        self.include_header = include_header
        self.prepend_ai_prompt = prepend_ai_prompt
        self.ai_prompt_text = ai_prompt_text
        self.append_footer = append_footer
        self.footer_text = footer_text
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            parts = split_text_balanced(
                text=self.text_buffer,
                mode=self.mode,
                limit_value=self.limit_value,
                num_parts=self.num_parts,
                cell_format=self.cell_format,
                coefficients_str=self.coefficients_str,
                include_header=self.include_header,
                prepend_ai_prompt=self.prepend_ai_prompt,
                ai_prompt_text=self.ai_prompt_text,
                append_footer=self.append_footer,
                footer_text=self.footer_text,
                cancel_check=lambda: self._is_cancelled,
            )
            if self._is_cancelled:
                self.cancelled_signal.emit()
            else:
                self.finished_signal.emit(parts, "Merged Content Splitting")
        except Exception as e:
            self.error_signal.emit(str(e))


class UpdateCheckWorker(QThread):
    check_finished = pyqtSignal(bool, str, str, str)  # (has_update, local_rev, remote_rev, error_message)
    pull_finished = pyqtSignal(bool, str)  # (success, message)

    def __init__(self, action: str = "check", repo_url: str = "https://github.com/serkanpaker/pytotext.git"):
        super().__init__()
        self.action = action
        self.repo_url = repo_url

    def run(self):
        if self.action == "check":
            try:
                # 1. Query remote HEAD commit hash
                res_remote = subprocess.run(
                    ["git", "ls-remote", self.repo_url, "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if res_remote.returncode != 0:
                    err = res_remote.stderr.strip() or "Could not reach remote repository."
                    self.check_finished.emit(False, "", "", err)
                    return

                remote_lines = res_remote.stdout.strip().split()
                if not remote_lines:
                    self.check_finished.emit(False, "", "", "Empty response from remote repository.")
                    return
                remote_rev = remote_lines[0]

                # 2. Get local HEAD commit hash if in a git repo
                local_rev = ""
                res_local = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=str(SCRIPT_DIR),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if res_local.returncode == 0:
                    local_rev = res_local.stdout.strip()

                if not local_rev:
                    # Not a git clone or no local commit
                    self.check_finished.emit(False, "", remote_rev, "LOCAL_NOT_GIT")
                    return

                has_update = (local_rev != remote_rev)
                self.check_finished.emit(has_update, local_rev, remote_rev, "")
            except Exception as e:
                self.check_finished.emit(False, "", "", str(e))

        elif self.action == "pull":
            try:
                # Try pull on main, fallback to master
                res_pull = subprocess.run(
                    ["git", "pull", "origin", "main", "--ff-only"],
                    cwd=str(SCRIPT_DIR),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if res_pull.returncode != 0:
                    res_pull = subprocess.run(
                        ["git", "pull", "origin", "master", "--ff-only"],
                        cwd=str(SCRIPT_DIR),
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )

                if res_pull.returncode == 0:
                    msg = res_pull.stdout.strip() or "Updated successfully."
                    self.pull_finished.emit(True, msg)
                else:
                    err_msg = res_pull.stderr.strip() or res_pull.stdout.strip() or "Failed to pull updates."
                    self.pull_finished.emit(False, err_msg)
            except Exception as e:
                self.pull_finished.emit(False, str(e))


# --------------------------------------------------
# Professional Design System & Theming Tokens
# --------------------------------------------------
def get_theme_stylesheet(mode: str) -> str:
    """
    Polished aesthetic with 8px smooth corner radii, clean symmetry, refined surface tiers,
    and elegant low-noise borders.
    """
    if mode == "dark":
        return """
        QMainWindow, QWidget {
            background-color: #0b0e14;
            color: #d6deeb;
            font-size: 11.5px;
        }

        /* Surfaces & Rounded Containers */
        QFrame#topBar, QFrame#navSidebar, QFrame#deckCard, QFrame#workflowBar, QFrame#viewerCard, QFrame#outputCard {
            background-color: #121722;
            border: 1px solid #1f2737;
            border-radius: 8px;
        }

        QFrame#innerCard {
            background-color: #0e121a;
            border: 1px solid #19202e;
            border-radius: 6px;
        }

        /* Splitters */
        QSplitter::handle {
            background-color: #19202e;
            margin: 0px 1px;
            border-radius: 3px;
        }
        QSplitter::handle:hover {
            background-color: #3b74f2;
        }
        QSplitter::handle:pressed {
            background-color: #2557c7;
        }

        /* Segmented Tabs */
        QTabWidget::pane {
            border: 1px solid #1f2737;
            background-color: #121722;
            border-radius: 8px;
        }
        QTabBar::tab {
            background-color: #0b0e14;
            color: #7e8b9b;
            padding: 5px 12px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            margin-right: 2px;
            border: 1px solid #19202e;
            border-bottom: none;
            font-weight: 500;
        }
        QTabBar::tab:selected {
            background-color: #121722;
            color: #4d8df7;
            font-weight: 600;
            border-color: #1f2737;
        }
        QTabBar::tab:hover:!selected {
            background-color: #151b28;
            color: #c5d1e0;
        }

        /* Standardized Buttons */
        QPushButton {
            background-color: #182030;
            color: #c5d1e0;
            border: 1px solid #243046;
            border-radius: 6px;
            padding: 4px 10px;
            min-height: 18px;
            font-weight: 500;
        }
        QPushButton:hover {
            background-color: #212c42;
            color: #ffffff;
            border-color: #3e5275;
        }
        QPushButton:pressed {
            background-color: #121722;
        }
        QPushButton:disabled {
            background-color: #0e121a;
            color: #4d5766;
            border-color: #19202e;
        }

        QPushButton#primaryActionBtn {
            background-color: #3267e6;
            color: #ffffff;
            font-weight: 600;
            border: 1px solid #4a7ffc;
            padding: 4px 14px;
        }
        QPushButton#primaryActionBtn:hover {
            background-color: #2659d6;
        }

        QPushButton#accentBtn {
            background-color: #162648;
            color: #79a6fc;
            border: 1px solid #28427a;
            font-weight: 600;
        }
        QPushButton#accentBtn:hover {
            background-color: #1e3463;
            color: #ffffff;
        }

        QPushButton#clearBtn {
            background-color: #182030;
            color: #7e8b9b;
            border: 1px solid #243046;
        }
        QPushButton#clearBtn:hover {
            background-color: #35171c;
            border-color: #d94841;
            color: #ff7d75;
        }

        /* Inputs & SpinBoxes */
        QLineEdit, QSpinBox, QComboBox {
            background-color: #0e121a;
            color: #d6deeb;
            border: 1px solid #202a3c;
            border-radius: 6px;
            padding: 4px 8px;
            min-height: 20px;
            selection-background-color: #244177;
            selection-color: #ffffff;
        }
        QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
            border: 1px solid #3b74f2;
        }

        QTextEdit {
            background-color: #0e121a;
            color: #d6deeb;
            border: 1px solid #202a3c;
            border-radius: 6px;
            padding: 4px 6px;
            selection-background-color: #244177;
            selection-color: #ffffff;
        }

        /* File Table */
        QTableWidget {
            background-color: #0e121a;
            color: #d6deeb;
            border: 1px solid #1f2737;
            border-radius: 6px;
            gridline-color: #151b28;
            selection-background-color: #17243c;
            selection-color: #eaf1fa;
        }
        QHeaderView::section {
            background-color: #121722;
            color: #7e8b9b;
            padding: 4px 6px;
            border: none;
            border-bottom: 1px solid #1f2737;
            border-right: 1px solid #19202e;
            font-weight: 600;
        }

        /* Status Bar */
        QStatusBar {
            background-color: #121722;
            color: #7e8b9b;
            border-top: 1px solid #1f2737;
            padding: 2px 8px;
        }
        """
    else:  # light mode
        return """
        QMainWindow, QWidget {
            background-color: #f1f4f8;
            color: #1b212d;
            font-size: 11.5px;
        }

        /* Surfaces & Rounded Containers */
        QFrame#topBar, QFrame#navSidebar, QFrame#deckCard, QFrame#workflowBar, QFrame#viewerCard, QFrame#outputCard {
            background-color: #ffffff;
            border: 1px solid #d9e1ec;
            border-radius: 8px;
        }

        QFrame#innerCard {
            background-color: #f7f9fc;
            border: 1px solid #e3e9f2;
            border-radius: 6px;
        }

        /* Splitters */
        QSplitter::handle {
            background-color: #d9e1ec;
            margin: 0px 1px;
            border-radius: 3px;
        }
        QSplitter::handle:hover {
            background-color: #3267e6;
        }
        QSplitter::handle:pressed {
            background-color: #1e4eb8;
        }

        /* Segmented Tabs */
        QTabWidget::pane {
            border: 1px solid #d9e1ec;
            background-color: #ffffff;
            border-radius: 8px;
        }
        QTabBar::tab {
            background-color: #eaeff6;
            color: #556274;
            padding: 5px 12px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            margin-right: 2px;
            border: 1px solid #d1dae8;
            border-bottom: none;
            font-weight: 500;
        }
        QTabBar::tab:selected {
            background-color: #ffffff;
            color: #2b61df;
            font-weight: 600;
            border-color: #d9e1ec;
        }
        QTabBar::tab:hover:!selected {
            background-color: #f1f5fa;
            color: #1b212d;
        }

        /* Standardized Buttons */
        QPushButton {
            background-color: #f5f8fc;
            color: #1b212d;
            border: 1px solid #cfd9e6;
            border-radius: 6px;
            padding: 4px 10px;
            min-height: 18px;
            font-weight: 500;
        }
        QPushButton:hover {
            background-color: #e9f0fa;
            color: #1d5ad6;
            border-color: #3267e6;
        }
        QPushButton:pressed {
            background-color: #dbe5f3;
        }
        QPushButton:disabled {
            background-color: #f5f8fc;
            color: #8c99ab;
            border-color: #e3e9f2;
        }

        QPushButton#primaryActionBtn {
            background-color: #3267e6;
            color: #ffffff;
            font-weight: 600;
            border: 1px solid #2354cd;
            padding: 4px 14px;
        }
        QPushButton#primaryActionBtn:hover {
            background-color: #2053cb;
        }

        QPushButton#accentBtn {
            background-color: #eaf1fe;
            color: #2354cd;
            border: 1px solid #bcccf5;
            font-weight: 600;
        }
        QPushButton#accentBtn:hover {
            background-color: #d9e6fd;
            color: #153ea4;
        }

        QPushButton#clearBtn {
            background-color: #f5f8fc;
            color: #556274;
            border: 1px solid #cfd9e6;
        }
        QPushButton#clearBtn:hover {
            background-color: #feeceb;
            border-color: #cc292b;
            color: #a0181a;
        }

        /* Inputs & SpinBoxes */
        QLineEdit, QSpinBox, QComboBox {
            background-color: #ffffff;
            color: #1b212d;
            border: 1px solid #cfd9e6;
            border-radius: 6px;
            padding: 4px 8px;
            min-height: 20px;
            selection-background-color: #b7d1ff;
            selection-color: #0b0e14;
        }
        QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
            border: 1px solid #3267e6;
        }

        QTextEdit {
            background-color: #ffffff;
            color: #1b212d;
            border: 1px solid #cfd9e6;
            border-radius: 6px;
            padding: 4px 6px;
            selection-background-color: #b7d1ff;
            selection-color: #0b0e14;
        }

        /* File Table */
        QTableWidget {
            background-color: #ffffff;
            color: #1b212d;
            border: 1px solid #d9e1ec;
            border-radius: 6px;
            gridline-color: #f1f4f8;
            selection-background-color: #e6effd;
            selection-color: #153ea4;
        }
        QHeaderView::section {
            background-color: #f5f8fc;
            color: #556274;
            padding: 4px 6px;
            border: none;
            border-bottom: 1px solid #cfd9e6;
            border-right: 1px solid #e7edf5;
            font-weight: 600;
        }

        /* Status Bar */
        QStatusBar {
            background-color: #ffffff;
            color: #556274;
            border-top: 1px solid #d9e1ec;
            padding: 2px 8px;
        }
        """


# --------------------------------------------------
# Code Editor with Line Gutter & Relaxed Line Height
# --------------------------------------------------
class LineNumberArea(QWidget):
    def __init__(self, editor: CodeEditorWithLineNumbers):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


class CodeEditorWithLineNumbers(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setUndoRedoEnabled(True)

        from PyQt6.QtGui import QFontDatabase
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        doc = self.document()
        doc.setDefaultFont(font)

        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)

        self.update_line_number_area_width(0)

    def line_number_area_width(self) -> int:
        digits = max(1, len(str(max(1, self.blockCount()))))
        space = 14 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        is_dark = self.palette().window().color().lightness() < 128
        bg_color = QColor("#0e121a") if is_dark else QColor("#eaeff6")
        fg_color = QColor("#596677") if is_dark else QColor("#8c99ab")
        border_color = QColor("#1f2737") if is_dark else QColor("#d1dae8")

        painter.fillRect(event.rect(), bg_color)
        painter.setPen(border_color)
        painter.drawLine(event.rect().topRight(), event.rect().bottomRight())

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        painter.setPen(fg_color)
        painter.setFont(self.font())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.drawText(0, top, self.line_number_area.width() - 6, self.fontMetrics().height(), Qt.AlignmentFlag.AlignRight, number)

            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1


# --------------------------------------------------
# Jupyter-Style Cell Renderer Widgets
# --------------------------------------------------
class JupiterCellWidget(QFrame):
    """A single renderable/editable cell in the Jupyter-style view."""
    move_up_signal = pyqtSignal(object)
    move_down_signal = pyqtSignal(object)
    delete_signal = pyqtSignal(object)

    def __init__(self, cell_data: dict, index: int, parent=None):
        super().__init__(parent)
        self.cell_data = cell_data
        self.cell_index = index
        self.hidden_prefix = cell_data.get("hidden_prefix", "")
        self.hidden_suffix = cell_data.get("hidden_suffix", "")
        self.setObjectName("jupiterCell")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Header Bar ---
        header = QFrame()
        header.setObjectName("jupiterCellHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header_layout.setSpacing(6)

        self.select_cb = QCheckBox()
        self.select_cb.setToolTip("Select this cell")
        header_layout.addWidget(self.select_cb)

        cell_type = cell_data.get("cell_type", "code")
        label_text = cell_data.get("cell_label", str(index + 1))
        type_badge = "Code" if cell_type == "code" else "Markdown"

        label = QLabel(f"<b>Cell {label_text}</b>")
        header_layout.addWidget(label)

        badge = QLabel(type_badge)
        badge.setObjectName("cellTypeBadge")
        badge_color = "#2d7ff9" if cell_type == "code" else "#18a058"
        badge.setStyleSheet(
            f"background: {badge_color}; color: white; padding: 1px 8px; "
            f"border-radius: 4px; font-size: 11px; font-weight: 600;"
        )
        header_layout.addWidget(badge)

        header_layout.addStretch()

        # Action buttons
        copy_btn = QPushButton("Copy")
        copy_btn.setFixedHeight(24)
        copy_btn.setToolTip("Copy cell content")
        copy_btn.clicked.connect(self._copy_cell)
        header_layout.addWidget(copy_btn)

        up_btn = QPushButton("▲")
        up_btn.setFixedSize(28, 24)
        up_btn.setToolTip("Move cell up")
        up_btn.clicked.connect(lambda: self.move_up_signal.emit(self))
        header_layout.addWidget(up_btn)

        down_btn = QPushButton("▼")
        down_btn.setFixedSize(28, 24)
        down_btn.setToolTip("Move cell down")
        down_btn.clicked.connect(lambda: self.move_down_signal.emit(self))
        header_layout.addWidget(down_btn)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(28, 24)
        del_btn.setToolTip("Delete cell")
        del_btn.setStyleSheet("color: #e05252; font-weight: bold;")
        del_btn.clicked.connect(lambda: self.delete_signal.emit(self))
        header_layout.addWidget(del_btn)

        layout.addWidget(header)

        # --- Editable Content Area ---
        self.editor = QPlainTextEdit()
        self.editor.setUndoRedoEnabled(True)
        self.raw_source = cell_data.get("source", "")
        self.editor.setPlainText(self.raw_source)

        from PyQt6.QtGui import QFontDatabase
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(11)
        self.editor.setFont(font)
        self.editor.document().setDefaultFont(font)

        # Auto-size: minimum 2 lines, grow with content
        line_count = max(2, self.raw_source.count("\n") + 1)
        line_height = self.editor.fontMetrics().lineSpacing()
        self.editor.setFixedHeight(min(line_count * line_height + 16, 400))

        layout.addWidget(self.editor)

    def set_markers_visible(self, visible: bool):
        """Toggle whether hidden syntax markers (fences, # %%) are shown in the cell editor."""
        current_text = self.editor.toPlainText()
        if visible:
            # Expand to show hidden prefix and suffix
            prefix_to_add = self.hidden_prefix if not current_text.startswith(self.hidden_prefix) else ""
            suffix_to_add = self.hidden_suffix if not current_text.endswith(self.hidden_suffix) else ""
            new_text = prefix_to_add + current_text + suffix_to_add
            self.editor.setPlainText(new_text)
        else:
            # Strip hidden prefix and suffix from current text
            new_text = current_text
            if self.hidden_prefix and new_text.startswith(self.hidden_prefix):
                new_text = new_text[len(self.hidden_prefix):]
            if self.hidden_suffix and new_text.endswith(self.hidden_suffix):
                new_text = new_text[:-len(self.hidden_suffix)]
            self.editor.setPlainText(new_text)

        # Auto-adjust height
        line_count = max(2, self.editor.toPlainText().count("\n") + 1)
        line_height = self.editor.fontMetrics().lineSpacing()
        self.editor.setFixedHeight(min(line_count * line_height + 16, 400))

    def _copy_cell(self):
        QApplication.clipboard().setText(self.editor.toPlainText())
        # Brief flash feedback
        sender = self.sender()
        if sender:
            original = sender.text()
            sender.setText("Copied!")
            QTimer.singleShot(1200, lambda: sender.setText(original))

    def get_content(self) -> str:
        """Returns visible editor content."""
        return self.editor.toPlainText()

    def get_reconstructed_content(self, markers_visible: bool = False) -> str:
        """Returns full content with hidden markers reconstructed."""
        text = self.editor.toPlainText()
        if markers_visible:
            return text
        return self.hidden_prefix + text + self.hidden_suffix

    def is_selected(self) -> bool:
        return self.select_cb.isChecked()


class JupiterNotebookView(QWidget):
    """Scrollable Jupyter-style cell list with toolbar."""
    back_to_editor_signal = pyqtSignal(str)

    def __init__(self, cells: List[dict], parent=None):
        super().__init__(parent)
        self.markers_visible = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # --- Toolbar ---
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 4, 4, 4)
        toolbar.setSpacing(8)

        self.select_all_cb = QCheckBox("Select All")
        self.select_all_cb.stateChanged.connect(self._toggle_select_all)
        toolbar.addWidget(self.select_all_cb)

        copy_selected_btn = QPushButton("Copy Selected")
        copy_selected_btn.setObjectName("primaryActionBtn")
        copy_selected_btn.clicked.connect(self._copy_selected)
        toolbar.addWidget(copy_selected_btn)

        # Show / Hide Syntax Markers Toggle Button
        self.toggle_markers_btn = QPushButton("Show Markers")
        self.toggle_markers_btn.setCheckable(True)
        self.toggle_markers_btn.setToolTip("Toggle visibility of # %%, ```python, and cell markers in editor cards")
        self.toggle_markers_btn.clicked.connect(self._toggle_markers_visibility)
        toolbar.addWidget(self.toggle_markers_btn)

        toolbar.addStretch()

        cell_count_label = QLabel(f"{len(cells)} cells")
        cell_count_label.setStyleSheet("color: #7e8b9b; font-size: 12px;")
        toolbar.addWidget(cell_count_label)
        self.cell_count_label = cell_count_label

        back_btn = QPushButton("◀ Back to Editor")
        back_btn.clicked.connect(self._go_back)
        toolbar.addWidget(back_btn)

        layout.addLayout(toolbar)

        # --- Scrollable Cell List ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.cell_container = QWidget()
        self.cell_layout = QVBoxLayout(self.cell_container)
        self.cell_layout.setContentsMargins(4, 4, 4, 4)
        self.cell_layout.setSpacing(6)

        self.cell_widgets: List[JupiterCellWidget] = []
        for i, cell_data in enumerate(cells):
            cw = JupiterCellWidget(cell_data, i)
            cw.move_up_signal.connect(self._move_cell_up)
            cw.move_down_signal.connect(self._move_cell_down)
            cw.delete_signal.connect(self._delete_cell)
            self.cell_widgets.append(cw)
            self.cell_layout.addWidget(cw)

        self.cell_layout.addStretch()
        scroll.setWidget(self.cell_container)
        layout.addWidget(scroll, 1)

    def _toggle_select_all(self, state):
        checked = state == Qt.CheckState.Checked.value
        for cw in self.cell_widgets:
            cw.select_cb.setChecked(checked)

    def _copy_selected(self):
        selected = [cw.get_content() for cw in self.cell_widgets if cw.is_selected()]
        if selected:
            QApplication.clipboard().setText("\n\n".join(selected))

    def _move_cell_up(self, cell_widget: JupiterCellWidget):
        idx = self.cell_widgets.index(cell_widget)
        if idx <= 0:
            return
        self._swap_cells(idx, idx - 1)

    def _move_cell_down(self, cell_widget: JupiterCellWidget):
        idx = self.cell_widgets.index(cell_widget)
        if idx >= len(self.cell_widgets) - 1:
            return
        self._swap_cells(idx, idx + 1)

    def _swap_cells(self, idx_a: int, idx_b: int):
        # Swap in list
        self.cell_widgets[idx_a], self.cell_widgets[idx_b] = (
            self.cell_widgets[idx_b], self.cell_widgets[idx_a]
        )

        # Rebuild layout order
        for i in range(self.cell_layout.count()):
            self.cell_layout.takeAt(0)

        for cw in self.cell_widgets:
            self.cell_layout.addWidget(cw)
        self.cell_layout.addStretch()

    def _toggle_markers_visibility(self):
        """Toggle whether hidden syntax markers (```python, # %%) are shown in all cell editors."""
        self.markers_visible = not self.markers_visible
        self.toggle_markers_btn.setText("Hide Markers" if self.markers_visible else "Show Markers")
        self.toggle_markers_btn.setChecked(self.markers_visible)
        for cw in self.cell_widgets:
            cw.set_markers_visible(self.markers_visible)

    def _delete_cell(self, cell_widget: JupiterCellWidget):
        if cell_widget in self.cell_widgets:
            self.cell_widgets.remove(cell_widget)
            self.cell_layout.removeWidget(cell_widget)
            cell_widget.deleteLater()
            self.cell_count_label.setText(f"{len(self.cell_widgets)} cells")

    def _go_back(self):
        """Reconstruct text from cells with all hidden markers preserved and emit back signal."""
        parts = [cw.get_reconstructed_content(markers_visible=self.markers_visible) for cw in self.cell_widgets]
        reconstructed = "".join(parts)
        self.back_to_editor_signal.emit(reconstructed)

    def get_all_content(self) -> str:
        parts = [cw.get_content() for cw in self.cell_widgets]
        return "\n\n".join(parts)


class CollapsibleSplitterHandle(QSplitterHandle):
    """
    Enhanced splitter handle that supports:
    - Double click to toggle full screen on the left pane
    - Visual hover cursor
    """
    def __init__(self, orientation: Qt.Orientation, parent: QSplitter):
        super().__init__(orientation, parent)
        self.setCursor(Qt.CursorShape.SplitHCursor)

    def mouseDoubleClickEvent(self, event):
        splitter = self.splitter()
        if isinstance(splitter, CollapsibleSplitter):
            splitter.toggle_fullscreen()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)


class CollapsibleSplitter(QSplitter):
    """
    A horizontal QSplitter that allows:
    - Expanding the left pane to 100% full width
    - Collapsing / restoring back to previous split proportions
    - Snapping to full screen if pulled all the way to the right
    """
    fullscreen_toggled = pyqtSignal(bool)  # is_fullscreen

    def __init__(self, orientation: Qt.Orientation = Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.is_left_fullscreen = False
        self.saved_sizes: List[int] = [320, 760]
        self.splitterMoved.connect(self._on_splitter_moved)

    def createHandle(self) -> QSplitterHandle:
        return CollapsibleSplitterHandle(self.orientation(), self)

    def toggle_fullscreen(self):
        if not self.is_left_fullscreen:
            # Save current non-maximized sizes if valid
            current_sizes = self.sizes()
            if len(current_sizes) >= 2 and current_sizes[1] > 20:
                self.saved_sizes = current_sizes
            
            total = sum(self.sizes())
            self.setSizes([total, 0])
            self.is_left_fullscreen = True
            self.fullscreen_toggled.emit(True)
        else:
            # Restore previous split proportions
            if not self.saved_sizes or self.saved_sizes[1] <= 20:
                total = sum(self.sizes())
                left = min(max(320, int(total * 0.35)), total - 100)
                self.saved_sizes = [left, total - left]
            self.setSizes(self.saved_sizes)
            self.is_left_fullscreen = False
            self.fullscreen_toggled.emit(False)

    def _on_splitter_moved(self, pos: int, index: int):
        sizes = self.sizes()
        if len(sizes) >= 2:
            right_width = sizes[1]
            total_width = sum(sizes)
            # If pulled within 25px of the right edge, snap to full screen
            if right_width <= 25 and not self.is_left_fullscreen:
                self.is_left_fullscreen = True
                self.fullscreen_toggled.emit(True)
            elif right_width > 25 and self.is_left_fullscreen:
                self.is_left_fullscreen = False
                self.fullscreen_toggled.emit(False)
            elif not self.is_left_fullscreen and right_width > 50:
                self.saved_sizes = sizes


# --------------------------------------------------
# Main Window Class
# --------------------------------------------------
class PyToTextMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyToText")
        app_icon = pytotext_assets.get_app_icon()
        if app_icon:
            self.setWindowIcon(app_icon)
        # Reduced minimum size so user can snap window to half of screen cleanly
        self.setMinimumSize(680, 480)
        self.resize(1080, 760)

        self.root_path: Optional[Path] = None
        self.recent_folders: List[str] = []
        self.discovered_files: Dict[str, Path] = {}
        self.file_char_map: Dict[str, int] = {}
        self.selected_files: Set[str] = set()
        self.cell_selection_map: Dict[str, Optional[List[str]]] = {}
        self.output_parts: List[str] = []

        self.current_theme_mode = "system"

        self.scan_worker: Optional[FolderScanWorker] = None
        self.char_worker: Optional[FolderCharCountWorker] = None
        self.merge_worker: Optional[FolderMergeWorker] = None
        self.process_worker: Optional[TextProcessWorker] = None

        self.split_timer = QTimer(self)
        self.split_timer.setSingleShot(True)
        self.split_timer.timeout.connect(self._show_stop_button)

        self._init_ui()
        self._load_config_session()
        self._update_workflow_state()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(6, 4, 6, 4)
        root_layout.setSpacing(6)

        # 1. Compact Utility Header Bar (No Presets button, clean utility)
        root_layout.addWidget(self._create_global_header())

        # 2. Main Outer Horizontal Splitter: Left Sidebar ↔ Right Workspace
        self.main_splitter = CollapsibleSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(True)
        self.main_splitter.fullscreen_toggled.connect(self._on_sidebar_fullscreen_toggled)

        # Left Sidebar Pane
        self.left_sidebar = self._create_left_sidebar_panel()
        self.left_sidebar.setMinimumWidth(260)
        self.main_splitter.addWidget(self.left_sidebar)

        # Right Workspace Pane
        self.right_workspace = self._create_right_workspace_panel()
        self.main_splitter.addWidget(self.right_workspace)

        self.main_splitter.setSizes([320, 760])
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)

        root_layout.addWidget(self.main_splitter, 1)

        # 3. Persistent Global Status Bar
        self._init_status_bar()

        # 4. Keyboard Shortcuts
        self._init_keyboard_shortcuts()

        # Apply initial theme
        self._apply_theme()

    def _create_global_header(self) -> QWidget:
        header_frame = QFrame()
        header_frame.setObjectName("topBar")
        header_frame.setFixedHeight(34)
        layout = QHBoxLayout(header_frame)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)

        # Top Left Brand Label with Logo
        brand_layout = QHBoxLayout()
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(8)

        logo_pixmap = pytotext_assets.get_logo_pixmap(24, 24)
        if logo_pixmap and not logo_pixmap.isNull():
            logo_label = QLabel()
            logo_label.setPixmap(logo_pixmap)
            logo_label.setFixedSize(24, 24)
            logo_label.setScaledContents(True)
            brand_layout.addWidget(logo_label)

        brand_label = QLabel("<b>PyToText</b>")
        brand_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #3b74f2; padding-left: 1px;")
        brand_layout.addWidget(brand_label)
        layout.addLayout(brand_layout)

        layout.addStretch()

        # Left Window Fullscreen / Split Toggle Button
        self.sidebar_toggle_btn = QPushButton("⛶ Fullscreen Left")
        self.sidebar_toggle_btn.setToolTip("Expand left window to full screen or restore split view (Cmd+B / Ctrl+B, or double-click divider)")
        self.sidebar_toggle_btn.clicked.connect(self._toggle_left_sidebar_fullscreen)
        layout.addWidget(self.sidebar_toggle_btn)

        # Appearance dropdown (◐ System ▾)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["◐ System", "☼ Light", "◑ Dark"])
        self.theme_combo.currentIndexChanged.connect(self._on_theme_combo_changed)
        layout.addWidget(self.theme_combo)

        # Check for Updates Button
        self.update_btn = QPushButton("🔄 Check Updates")
        self.update_btn.setToolTip("Check for updates on GitHub (https://github.com/serkanpaker/pytotext.git)")
        self.update_btn.clicked.connect(self._check_for_updates)
        layout.addWidget(self.update_btn)

        # Settings Button (⚙ Settings)
        config_btn = QPushButton("⚙ Settings")
        config_btn.setToolTip("Export / Import Configuration JSON")
        config_menu = QMenu(self)
        save_cfg_act = config_menu.addAction("Export Config JSON...")
        save_cfg_act.triggered.connect(self._export_config_json)
        load_cfg_act = config_menu.addAction("Import Config JSON...")
        load_cfg_act.triggered.connect(self._import_config_json)
        config_menu.addSeparator()
        reset_cfg_act = config_menu.addAction("Reset to Defaults")
        reset_cfg_act.triggered.connect(self._reset_to_default_settings)
        config_btn.setMenu(config_menu)
        layout.addWidget(config_btn)

        return header_frame

    def _create_left_sidebar_panel(self) -> QWidget:
        container = QFrame()
        container.setObjectName("navSidebar")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.addTab(self._create_folder_browser_tab(), "Source Files")
        self.sidebar_tabs.addTab(self._create_quick_paste_tab(), "Quick Paste")
        layout.addWidget(self.sidebar_tabs)

        return container

    def _create_folder_browser_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(2, 4, 2, 4)
        layout.setSpacing(6)

        # Directory bar
        dir_frame = QFrame()
        dir_frame.setObjectName("innerCard")
        dir_layout = QHBoxLayout(dir_frame)
        dir_layout.setContentsMargins(6, 4, 6, 4)
        dir_layout.setSpacing(4)

        open_btn = QPushButton("Choose Folder…")
        open_btn.setToolTip("Open source folder (Cmd+O / Ctrl+O)")
        open_btn.clicked.connect(self._select_folder)
        dir_layout.addWidget(open_btn)

        self.path_display_label = QLabel("<i>No folder selected</i>")
        self.path_display_label.setStyleSheet("color: #7e8b9b;")
        self.path_display_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        dir_layout.addWidget(self.path_display_label, 1)

        self.dir_menu_btn = QToolButton()
        self.dir_menu_btn.setText("•••")
        self.dir_menu_btn.setToolTip("Directory actions")
        self.dir_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        dir_menu = QMenu(self)
        rescan_act = dir_menu.addAction("Rescan Directory")
        rescan_act.triggered.connect(lambda: self._scan_directory(self.root_path) if self.root_path else None)
        reveal_act = dir_menu.addAction("Reveal in Finder / Explorer")
        reveal_act.triggered.connect(self._reveal_current_folder)
        copy_path_act = dir_menu.addAction("Copy Directory Path")
        copy_path_act.triggered.connect(self._copy_current_folder_path)
        dir_menu.addSeparator()
        self.recent_menu = dir_menu.addMenu("Recent Folders")
        self.dir_menu_btn.setMenu(dir_menu)
        dir_layout.addWidget(self.dir_menu_btn)

        layout.addWidget(dir_frame)

        # Search Bar & Category Filter
        search_layout = QHBoxLayout()
        search_layout.setSpacing(4)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("⌕ Search files…")
        self.search_input.textChanged.connect(self._filter_file_tree)
        search_layout.addWidget(self.search_input, 1)

        self.category_combo = QComboBox()
        self.category_combo.addItems(["All Files", "Code (.py, .js…)", "Docs (.md, .txt…)", "Notebooks (.ipynb)"])
        self.category_combo.currentIndexChanged.connect(self._apply_preset_filter)
        search_layout.addWidget(self.category_combo)
        layout.addLayout(search_layout)

        # Tree-view File Browser (columns: Name, Size, Chars, Tokens)
        self.file_tree = QTreeWidget()
        self.file_tree.setColumnCount(4)
        self.file_tree.setHeaderLabels(["Name", "Size", "Chars", "Tokens"])
        header = self.file_tree.header()
        # Name column: user can drag to resize
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setDefaultSectionSize(220)
        header.setStretchLastSection(False)
        self.file_tree.setColumnWidth(0, 260)
        self.file_tree.setSortingEnabled(True)
        self.file_tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.file_tree.setUniformRowHeights(True)
        self.file_tree.setAnimated(True)
        self.file_tree.setIndentation(16)
        self.file_tree.setRootIsDecorated(True)
        self.file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self._show_file_tree_context_menu)
        self.file_tree.itemChanged.connect(self._on_tree_item_changed)
        self.file_tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        layout.addWidget(self.file_tree, 1)

        # Batch Selection Bar
        batch_frame = QFrame()
        batch_frame.setObjectName("innerCard")
        batch_layout = QVBoxLayout(batch_frame)
        batch_layout.setContentsMargins(6, 4, 6, 4)
        batch_layout.setSpacing(4)

        stats_row = QHBoxLayout()
        self.discovery_stats_label = QLabel("0 files discovered")
        self.discovery_stats_label.setStyleSheet("color: #7e8b9b;")
        stats_row.addWidget(self.discovery_stats_label)

        stats_row.addStretch()

        self.selection_stats_label = QLabel("0 selected")
        self.selection_stats_label.setStyleSheet("font-weight: bold; color: #3b74f2;")
        stats_row.addWidget(self.selection_stats_label)
        batch_layout.addLayout(stats_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        sel_all_btn = QPushButton("Select All")
        sel_all_btn.clicked.connect(self._select_all_files)
        btn_row.addWidget(sel_all_btn)

        desel_all_btn = QPushButton("Deselect All")
        desel_all_btn.clicked.connect(self._clear_file_selection)
        btn_row.addWidget(desel_all_btn)

        calc_btn = QPushButton("Estimates")
        calc_btn.setToolTip("Calculate exact character and token estimates for discovered files")
        calc_btn.clicked.connect(self._calculate_file_char_sizes)
        btn_row.addWidget(calc_btn)

        batch_layout.addLayout(btn_row)
        layout.addWidget(batch_frame)

        return tab

    def _create_quick_paste_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(2, 4, 2, 4)
        layout.setSpacing(6)

        # Stacked widget: page 0 = raw editor, page 1 = jupyter notebook view
        self.paste_stack = QStackedWidget()

        # --- Page 0: Raw Text Editor ---
        editor_page = QWidget()
        editor_layout = QVBoxLayout(editor_page)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(6)

        self.paste_text_edit = CodeEditorWithLineNumbers()
        self.paste_text_edit.setPlaceholderText(
            "# Paste raw Python code, Jupyter notebook source, Markdown, or text here...\n\n"
            "# Cell 1:\nprint('Hello PyToText v2')\n\n"
            "# Cell 2:\n..."
        )
        editor_layout.addWidget(self.paste_text_edit, 1)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(6)
        self.paste_stats_label = QLabel("0 chars · 0 tokens")
        self.paste_stats_label.setStyleSheet("color: #7e8b9b;")
        bottom_row.addWidget(self.paste_stats_label)

        bottom_row.addStretch()

        # Render Jupyter button (hidden by default, shown when markers detected)
        self.render_jupyter_btn = QPushButton("Render Jupyter")
        self.render_jupyter_btn.setObjectName("primaryActionBtn")
        self.render_jupyter_btn.setToolTip("Render as Jupyter-style cells")
        self.render_jupyter_btn.setVisible(False)
        self.render_jupyter_btn.clicked.connect(self._render_jupyter_view)
        bottom_row.addWidget(self.render_jupyter_btn)

        clear_paste_btn = QPushButton("Clear")
        clear_paste_btn.setObjectName("clearBtn")
        clear_paste_btn.clicked.connect(lambda: self.paste_text_edit.clear())
        bottom_row.addWidget(clear_paste_btn)

        self.paste_text_edit.textChanged.connect(self._update_paste_stats)
        editor_layout.addLayout(bottom_row)

        self.paste_stack.addWidget(editor_page)

        # --- Page 1: Jupyter Notebook View (placeholder, built dynamically) ---
        self.jupyter_placeholder = QWidget()
        self.paste_stack.addWidget(self.jupyter_placeholder)

        layout.addWidget(self.paste_stack, 1)

        return tab


    def _create_right_workspace_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 1. Responsive Configuration & Budget Deck
        layout.addWidget(self._create_config_deck())

        # 2. Workflow Actions Bar
        layout.addWidget(self._create_workflow_toolbar())

        # 3. Draggable Workspace Splitter (Upper Merged Viewer ↕ Lower Split Parts)
        self.workspace_splitter = QSplitter(Qt.Orientation.Vertical)
        self.workspace_splitter.setChildrenCollapsible(False)

        self.merged_viewer_card = self._create_merged_viewer_card()
        self.split_parts_card = self._create_split_parts_card()

        self.workspace_splitter.addWidget(self.merged_viewer_card)
        self.workspace_splitter.addWidget(self.split_parts_card)
        self.workspace_splitter.setSizes([380, 380])
        self.workspace_splitter.setStretchFactor(0, 1)
        self.workspace_splitter.setStretchFactor(1, 1)

        layout.addWidget(self.workspace_splitter, 1)

        return container

    def _create_config_deck(self) -> QWidget:
        deck_card = QFrame()
        deck_card.setObjectName("deckCard")
        layout = QVBoxLayout(deck_card)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(6)

        title_row = QHBoxLayout()
        title_lbl = QLabel("<b>Configuration & Limit</b>")
        title_lbl.setStyleSheet("color: #7e8b9b; font-size: 11px;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        layout.addLayout(title_row)

        # Parameter Grid with 3 Modes: Max Chars / Part, Max Tokens / Part, Fixed N Parts
        self.config_grid_layout = QGridLayout()
        self.config_grid_layout.setHorizontalSpacing(10)
        self.config_grid_layout.setVerticalSpacing(6)

        # Mode
        self.config_grid_layout.addWidget(QLabel("Mode:"), 0, 0)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Max Chars / Part", "Max Tokens / Part", "Fixed N Parts"])
        self.mode_combo.setMinimumWidth(130)
        self.mode_combo.currentIndexChanged.connect(self._on_split_mode_changed)
        self.config_grid_layout.addWidget(self.mode_combo, 0, 1)

        # Limit
        self.budget_label = QLabel("Limit:")
        self.config_grid_layout.addWidget(self.budget_label, 0, 2)
        self.max_chars_spin = QSpinBox()
        self.max_chars_spin.setRange(10, 10000000)
        self.max_chars_spin.setValue(pytotext2.DEFAULT_MAX_CHARS)
        self.max_chars_spin.setSingleStep(5000)
        self.max_chars_spin.setGroupSeparatorShown(True)
        self.max_chars_spin.setMinimumWidth(95)
        self.config_grid_layout.addWidget(self.max_chars_spin, 0, 3)

        self.parts_spin = QSpinBox()
        self.parts_spin.setRange(1, 100)
        self.parts_spin.setValue(pytotext2.DEFAULT_NUM_PARTS)
        self.parts_spin.setMinimumWidth(60)
        self.parts_spin.hide()
        self.config_grid_layout.addWidget(self.parts_spin, 0, 3)

        # Multipliers
        self.config_grid_layout.addWidget(QLabel("Multipliers:"), 0, 4)
        self.custom_pattern_input = QLineEdit()
        self.custom_pattern_input.setPlaceholderText("e.g. 1.5, 1.0 or 2:1")
        self.custom_pattern_input.setMinimumWidth(100)
        self.custom_pattern_input.setMaximumWidth(200)
        self.custom_pattern_input.setToolTip(
            "Multipliers Guide:\n"
            "• Positive numbers (e.g. '1.5, 1.0' or '2:1:1').\n"
            "• Fixed N Parts Mode: weights parts proportionally.\n"
            "• Max Chars/Tokens Mode: scales targets up to limit ceiling.\n"
            "• Leave blank for equal distribution."
        )
        self.config_grid_layout.addWidget(self.custom_pattern_input, 0, 5)

        layout.addLayout(self.config_grid_layout)

        # Row 2: Side-by-side multiline editors
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        # AI Prompt Group
        ai_frame = QFrame()
        ai_frame.setObjectName("innerCard")
        ai_layout = QVBoxLayout(ai_frame)
        ai_layout.setContentsMargins(6, 4, 6, 4)
        ai_layout.setSpacing(3)

        ai_header = QHBoxLayout()
        self.chk_ai_prompt = QCheckBox("AI Context / Prompt")
        self.chk_ai_prompt.setChecked(True)
        ai_header.addWidget(self.chk_ai_prompt)

        ai_header.addStretch()

        self.ai_prompt_count_label = QLabel("0 chars")
        self.ai_prompt_count_label.setStyleSheet("color: #7e8b9b; font-size: 10px;")
        ai_header.addWidget(self.ai_prompt_count_label)
        ai_layout.addLayout(ai_header)

        self.ai_prompt_edit = QTextEdit()
        self.ai_prompt_edit.setPlainText('Just say "I understood". I will share the prompt later.')
        self.ai_prompt_edit.setMaximumHeight(44)
        self.ai_prompt_edit.textChanged.connect(self._update_ai_prompt_counter)
        self.chk_ai_prompt.toggled.connect(self.ai_prompt_edit.setEnabled)
        ai_layout.addWidget(self.ai_prompt_edit)
        row2.addWidget(ai_frame, 1)

        # Part Formatting Group
        format_frame = QFrame()
        format_frame.setObjectName("innerCard")
        format_layout = QVBoxLayout(format_frame)
        format_layout.setContentsMargins(6, 4, 6, 4)
        format_layout.setSpacing(3)

        format_header = QHBoxLayout()
        self.chk_part_header = QCheckBox("Part Titles")
        self.chk_part_header.setChecked(True)
        format_header.addWidget(self.chk_part_header)

        self.chk_part_footer = QCheckBox("Footer Template")
        self.chk_part_footer.setChecked(False)
        format_header.addWidget(self.chk_part_footer)

        format_header.addStretch()

        vars_lbl = QLabel("Variables: {part}, {total_parts}")
        vars_lbl.setStyleSheet("color: #7e8b9b; font-size: 10px;")
        format_header.addWidget(vars_lbl)
        format_layout.addLayout(format_header)

        self.footer_edit = QTextEdit()
        self.footer_edit.setPlainText("--- End of Part {part} of {total_parts} ---")
        self.footer_edit.setMaximumHeight(44)
        self.footer_edit.setEnabled(False)
        self.chk_part_footer.toggled.connect(self.footer_edit.setEnabled)
        format_layout.addWidget(self.footer_edit)
        row2.addWidget(format_frame, 1)

        layout.addLayout(row2)
        self._update_ai_prompt_counter()
        return deck_card

    def _create_workflow_toolbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("workflowBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Pipeline actions with dynamic focus
        self.btn_merge = QPushButton("Merge into Viewer")
        self.btn_merge.setObjectName("primaryActionBtn")
        self.btn_merge.setToolTip("Merge selected files into text viewer (Cmd+Shift+M)")
        self.btn_merge.clicked.connect(self._merge_selected_files_to_viewer)
        layout.addWidget(self.btn_merge)

        self.btn_tree = QPushButton("Generate Tree")
        self.btn_tree.setToolTip("Generate ASCII hierarchical tree of selected files")
        self.btn_tree.clicked.connect(self._insert_folder_tree_into_viewer)
        layout.addWidget(self.btn_tree)

        self.btn_split = QPushButton("Split into Parts")
        self.btn_split.setToolTip("Split merged text into balanced chunks (Cmd+Shift+S)")
        self.btn_split.clicked.connect(self._split_merged_viewer_text)
        layout.addWidget(self.btn_split)

        self.btn_export = QPushButton("Export Parts…")
        self.btn_export.setToolTip("Export generated parts to disk (Cmd+E)")
        self.btn_export.clicked.connect(self._export_output_files)
        layout.addWidget(self.btn_export)

        layout.addStretch()

        self.stop_op_btn = QPushButton("⏹ Stop")
        self.stop_op_btn.setObjectName("clearBtn")
        self.stop_op_btn.hide()
        self.stop_op_btn.clicked.connect(self._cancel_split_operation)
        layout.addWidget(self.stop_op_btn)

        return bar

    def _create_merged_viewer_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("viewerCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        header_row = QHBoxLayout()
        self.viewer_title_label = QLabel("<b>Merged Text Viewer</b>")
        self.viewer_title_label.setStyleSheet("color: #7e8b9b; font-size: 11px;")
        header_row.addWidget(self.viewer_title_label)

        header_row.addStretch()

        find_btn = QPushButton("Find & Replace")
        find_btn.setToolTip("Toggle Find & Replace Bar (Cmd+F / Ctrl+F)")
        find_btn.clicked.connect(self._toggle_find_replace_bar)
        header_row.addWidget(find_btn)

        self.copy_viewer_btn = QPushButton("Copy")
        self.copy_viewer_btn.setToolTip("Copy entire merged viewer text to clipboard")
        self.copy_viewer_btn.setEnabled(False)
        self.copy_viewer_btn.clicked.connect(lambda: self._copy_to_clipboard(self.merged_text_edit.toPlainText(), self.copy_viewer_btn))
        header_row.addWidget(self.copy_viewer_btn)

        self.save_viewer_btn = QPushButton("Save As…")
        self.save_viewer_btn.setToolTip("Save merged text to a file (.py, .md, .txt, etc.)")
        self.save_viewer_btn.setEnabled(False)
        self.save_viewer_btn.clicked.connect(self._save_merged_viewer_file)
        header_row.addWidget(self.save_viewer_btn)

        self.clear_viewer_btn = QPushButton("Clear")
        self.clear_viewer_btn.setObjectName("clearBtn")
        self.clear_viewer_btn.setToolTip("Clear viewer buffer")
        self.clear_viewer_btn.setEnabled(False)
        self.clear_viewer_btn.clicked.connect(self._clear_merged_viewer)
        header_row.addWidget(self.clear_viewer_btn)

        layout.addLayout(header_row)

        self.find_replace_widget = self._create_find_replace_bar()
        layout.addWidget(self.find_replace_widget)

        # Stack for Intentional Empty State vs Code Editor
        self.viewer_stack = QStackedWidget()

        # Page 0: Intentional Empty State
        empty_widget = QWidget()
        empty_layout = QVBoxLayout(empty_widget)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_title = QLabel("<b>Nothing merged yet</b>")
        empty_title.setStyleSheet("font-size: 13px; color: #7e8b9b;")
        empty_sub = QLabel("Select source files from the sidebar and merge them into one context,\nor generate an ASCII folder tree.")
        empty_sub.setStyleSheet("color: #7e8b9b; margin-bottom: 8px;")
        empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_btn_box = QHBoxLayout()
        m_btn = QPushButton("Merge Selected Files")
        m_btn.setObjectName("accentBtn")
        m_btn.clicked.connect(self._merge_selected_files_to_viewer)
        t_btn = QPushButton("Generate Tree")
        t_btn.clicked.connect(self._insert_folder_tree_into_viewer)
        empty_btn_box.addStretch()
        empty_btn_box.addWidget(m_btn)
        empty_btn_box.addWidget(t_btn)
        empty_btn_box.addStretch()

        empty_layout.addWidget(empty_title, alignment=Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_sub, alignment=Qt.AlignmentFlag.AlignCenter)
        empty_layout.addLayout(empty_btn_box)
        self.viewer_stack.addWidget(empty_widget)

        # Page 1: Code Editor
        self.merged_text_edit = CodeEditorWithLineNumbers()
        self.merged_text_edit.textChanged.connect(self._update_viewer_stats)
        self.viewer_stack.addWidget(self.merged_text_edit)

        layout.addWidget(self.viewer_stack, 1)

        # Footer stats
        footer_row = QHBoxLayout()
        self.viewer_stats_label = QLabel("0 chars · 0 tokens · 0 files merged")
        self.viewer_stats_label.setStyleSheet("color: #7e8b9b; font-size: 10.5px;")
        footer_row.addWidget(self.viewer_stats_label)
        footer_row.addStretch()
        layout.addLayout(footer_row)

        return card

    def _create_find_replace_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("innerCard")
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        r1 = QHBoxLayout()
        r1.setSpacing(4)
        r1.addWidget(QLabel("Find:"))
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Search in document (Enter for next)...")
        self.find_input.textChanged.connect(self._on_find_text_changed)
        self.find_input.returnPressed.connect(self._find_next)
        r1.addWidget(self.find_input, 1)

        self.match_count_label = QLabel("0 matches")
        self.match_count_label.setStyleSheet("color: #7e8b9b; font-size: 10px;")
        r1.addWidget(self.match_count_label)

        prev_btn = QPushButton("Prev")
        prev_btn.clicked.connect(self._find_prev)
        r1.addWidget(prev_btn)

        next_btn = QPushButton("Next")
        next_btn.clicked.connect(self._find_next)
        r1.addWidget(next_btn)

        self.chk_match_case = QCheckBox("Case")
        self.chk_match_case.toggled.connect(self._on_find_text_changed)
        r1.addWidget(self.chk_match_case)

        close_btn = QPushButton("✕")
        close_btn.setFixedWidth(24)
        close_btn.clicked.connect(lambda: self.find_replace_widget.hide())
        r1.addWidget(close_btn)
        layout.addLayout(r1)

        r2 = QHBoxLayout()
        r2.setSpacing(4)
        r2.addWidget(QLabel("Replace:"))
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Replacement text...")
        r2.addWidget(self.replace_input, 1)

        rep_next_btn = QPushButton("Replace Next")
        rep_next_btn.clicked.connect(self._replace_next)
        r2.addWidget(rep_next_btn)

        rep_all_btn = QPushButton("Replace All")
        rep_all_btn.setObjectName("accentBtn")
        rep_all_btn.clicked.connect(self._replace_all)
        r2.addWidget(rep_all_btn)
        layout.addLayout(r2)

        bar.hide()
        return bar

    def _create_split_parts_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("outputCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        header_row = QHBoxLayout()
        self.output_title_label = QLabel("<b>Split Output Preview</b>")
        self.output_title_label.setStyleSheet("color: #7e8b9b; font-size: 11px;")
        header_row.addWidget(self.output_title_label)

        header_row.addStretch()

        self.total_output_stats_label = QLabel("0 parts · 0 chars · 0 tokens")
        self.total_output_stats_label.setStyleSheet("color: #7e8b9b; font-weight: 500;")
        header_row.addWidget(self.total_output_stats_label)

        self.copy_all_btn = QPushButton("Copy All")
        self.copy_all_btn.setToolTip("Copy all parts combined with delimiters to clipboard")
        self.copy_all_btn.setEnabled(False)
        self.copy_all_btn.clicked.connect(self._copy_all_parts)
        header_row.addWidget(self.copy_all_btn)

        self.clear_out_btn = QPushButton("Clear")
        self.clear_out_btn.setObjectName("clearBtn")
        self.clear_out_btn.setEnabled(False)
        self.clear_out_btn.clicked.connect(self._clear_output_parts)
        header_row.addWidget(self.clear_out_btn)

        layout.addLayout(header_row)

        # Output Stack: Intentional Empty State vs Tabs
        self.output_stack = QStackedWidget()

        # Page 0: Intentional Empty State
        empty_split = QWidget()
        empty_split_layout = QVBoxLayout(empty_split)
        empty_split_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        es_title = QLabel("<b>No parts generated yet</b>")
        es_title.setStyleSheet("font-size: 13px; color: #7e8b9b;")
        es_sub = QLabel("Split the merged content according to the active limit to inspect output chunks.")
        es_sub.setStyleSheet("color: #7e8b9b; margin-bottom: 8px;")
        es_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        es_btn_box = QHBoxLayout()
        es_btn = QPushButton("Split into Parts")
        es_btn.clicked.connect(self._split_merged_viewer_text)
        es_btn_box.addStretch()
        es_btn_box.addWidget(es_btn)
        es_btn_box.addStretch()

        empty_split_layout.addWidget(es_title, alignment=Qt.AlignmentFlag.AlignCenter)
        empty_split_layout.addWidget(es_sub, alignment=Qt.AlignmentFlag.AlignCenter)
        empty_split_layout.addLayout(es_btn_box)
        self.output_stack.addWidget(empty_split)

        # Page 1: Tab Container for generated parts
        self.output_tabs = QTabWidget()
        self.output_stack.addWidget(self.output_tabs)

        layout.addWidget(self.output_stack, 1)
        self._clear_output_parts()

        return card

    def _init_status_bar(self):
        sb = self.statusBar()
        sb.setSizeGripEnabled(False)
        self.status_state_label = QLabel("● Ready")
        self.status_state_label.setStyleSheet("font-weight: bold; color: #2da44e;")
        sb.addWidget(self.status_state_label)

        self.status_msg_label = QLabel("Open a folder or paste text to begin.")
        sb.addWidget(self.status_msg_label, 1)

        self.status_metrics_label = QLabel("Selected: 0 files (0 B) | Merged: 0 chars · ~0 tokens")
        self.status_metrics_label.setStyleSheet("color: #7e8b9b;")
        sb.addPermanentWidget(self.status_metrics_label)

    def _init_keyboard_shortcuts(self):
        # Open Folder (Ctrl+O / Cmd+O)
        open_act = QAction(self)
        open_act.setShortcuts([QKeySequence("Ctrl+O"), QKeySequence("Meta+O")])
        open_act.triggered.connect(self._select_folder)
        self.addAction(open_act)

        # Refresh / Rescan Directory (Ctrl+R / Cmd+R)
        refresh_act = QAction(self)
        refresh_act.setShortcuts([QKeySequence("Ctrl+R"), QKeySequence("Meta+R")])
        refresh_act.triggered.connect(lambda: self._scan_directory(self.root_path) if self.root_path else None)
        self.addAction(refresh_act)

        # Select All Files (Ctrl+A / Cmd+A - only when tree is focused or globally when appropriate)
        sel_all_act = QAction(self)
        sel_all_act.setShortcuts([QKeySequence("Ctrl+Alt+A"), QKeySequence("Meta+Alt+A")])
        sel_all_act.triggered.connect(self._select_all_files)
        self.addAction(sel_all_act)

        # Deselect All Files (Ctrl+D / Cmd+D)
        desel_act = QAction(self)
        desel_act.setShortcuts([QKeySequence("Ctrl+D"), QKeySequence("Meta+D")])
        desel_act.triggered.connect(self._clear_file_selection)
        self.addAction(desel_act)

        # Focus Search Bar (Ctrl+F / Cmd+F)
        find_act = QAction(self)
        find_act.setShortcuts([QKeySequence("Ctrl+F"), QKeySequence("Meta+F")])
        find_act.triggered.connect(self._focus_search_or_toggle_find)
        self.addAction(find_act)

        # Generate & Preview / Merge (Ctrl+G / Cmd+G)
        gen_act = QAction(self)
        gen_act.setShortcuts([QKeySequence("Ctrl+G"), QKeySequence("Meta+G")])
        gen_act.triggered.connect(self._merge_selected_files_to_viewer)
        self.addAction(gen_act)

        # Legacy Merge Shortcut (Ctrl+Shift+M / Cmd+Shift+M)
        merge_act = QAction(self)
        merge_act.setShortcuts([QKeySequence("Ctrl+Shift+M"), QKeySequence("Meta+Shift+M")])
        merge_act.triggered.connect(self._merge_selected_files_to_viewer)
        self.addAction(merge_act)

        # Split into parts (Ctrl+Shift+S / Cmd+Shift+S)
        split_act = QAction(self)
        split_act.setShortcuts([QKeySequence("Ctrl+Shift+S"), QKeySequence("Meta+Shift+S")])
        split_act.triggered.connect(self._split_merged_viewer_text)
        self.addAction(split_act)

        # Save Active Part / Merged File (Ctrl+S / Cmd+S)
        save_act = QAction(self)
        save_act.setShortcuts([QKeySequence("Ctrl+S"), QKeySequence("Meta+S")])
        save_act.triggered.connect(self._save_active_part_or_viewer)
        self.addAction(save_act)

        # Copy Active Part / Merged Content (Ctrl+Shift+C / Cmd+Shift+C)
        copy_act = QAction(self)
        copy_act.setShortcuts([QKeySequence("Ctrl+Shift+C"), QKeySequence("Meta+Shift+C")])
        copy_act.triggered.connect(self._copy_active_part_or_viewer)
        self.addAction(copy_act)

        # Export All Generated Files (Ctrl+E / Cmd+E)
        export_act = QAction(self)
        export_act.setShortcuts([QKeySequence("Ctrl+E"), QKeySequence("Meta+E")])
        export_act.triggered.connect(self._export_output_files)
        self.addAction(export_act)

        # Toggle Dark/Light Theme (Ctrl+T / Cmd+T)
        theme_act = QAction(self)
        theme_act.setShortcuts([QKeySequence("Ctrl+T"), QKeySequence("Meta+T")])
        theme_act.triggered.connect(self._toggle_theme_mode)
        self.addAction(theme_act)

        # Undo (Ctrl+Z / Cmd+Z)
        undo_act = QAction(self)
        undo_act.setShortcuts([QKeySequence("Ctrl+Z"), QKeySequence("Meta+Z")])
        undo_act.triggered.connect(self._undo_focused_editor)
        self.addAction(undo_act)

        # Redo (Ctrl+Y / Cmd+Y / Ctrl+Shift+Z / Cmd+Shift+Z)
        redo_act = QAction(self)
        redo_act.setShortcuts([
            QKeySequence("Ctrl+Y"), QKeySequence("Meta+Y"),
            QKeySequence("Ctrl+Shift+Z"), QKeySequence("Meta+Shift+Z"),
        ])
        redo_act.triggered.connect(self._redo_focused_editor)
        self.addAction(redo_act)

        # Toggle Left Sidebar Fullscreen (Ctrl+B / Cmd+B)
        toggle_sidebar_act = QAction(self)
        toggle_sidebar_act.setShortcuts([QKeySequence("Ctrl+B"), QKeySequence("Meta+B")])
        toggle_sidebar_act.triggered.connect(self._toggle_left_sidebar_fullscreen)
        self.addAction(toggle_sidebar_act)

    def _toggle_left_sidebar_fullscreen(self):
        if hasattr(self, "main_splitter"):
            self.main_splitter.toggle_fullscreen()

    def _on_sidebar_fullscreen_toggled(self, is_fullscreen: bool):
        if hasattr(self, "sidebar_toggle_btn"):
            if is_fullscreen:
                self.sidebar_toggle_btn.setText("↔ Restore Split")
                self.sidebar_toggle_btn.setToolTip("Restore split layout (Cmd+B / Ctrl+B, or double-click divider)")
                self.statusBar().showMessage("Left window expanded to full width. Press Cmd+B or double-click divider to restore.", 4000)
            else:
                self.sidebar_toggle_btn.setText("⛶ Fullscreen Left")
                self.sidebar_toggle_btn.setToolTip("Expand left window to full screen (Cmd+B / Ctrl+B, or double-click divider)")
                self.statusBar().showMessage("Split layout restored.", 3000)

    def _get_focused_editor(self) -> Optional[QPlainTextEdit]:
        """Return the QPlainTextEdit that currently has keyboard focus, if any."""
        widget = QApplication.focusWidget()
        while widget is not None:
            if isinstance(widget, QPlainTextEdit):
                return widget
            widget = widget.parent() if hasattr(widget, 'parent') else None
        return None

    def _undo_focused_editor(self):
        editor = self._get_focused_editor()
        if editor and editor.document().isUndoAvailable():
            editor.undo()

    def _redo_focused_editor(self):
        editor = self._get_focused_editor()
        if editor and editor.document().isRedoAvailable():
            editor.redo()

    def _focus_search_or_toggle_find(self):
        if hasattr(self, "search_input") and self.search_input.isVisible():
            self.search_input.setFocus()
            self.search_input.selectAll()
        else:
            self._toggle_find_replace_bar()

    def _toggle_theme_mode(self):
        if hasattr(self, "theme_combo"):
            idx = (self.theme_combo.currentIndex() + 1) % self.theme_combo.count()
            self.theme_combo.setCurrentIndex(idx)

    # --------------------------------------------------
    # Theme Management
    # --------------------------------------------------
    def _on_theme_combo_changed(self, index: int):
        themes = ["system", "light", "dark"]
        self.current_theme_mode = themes[index]
        self._apply_theme()
        self._save_config_session()

    def _apply_theme(self):
        mode = self.current_theme_mode
        if mode == "system":
            is_dark = QApplication.palette().window().color().lightness() < 128
            applied_mode = "dark" if is_dark else "light"
        else:
            applied_mode = mode

        self.setStyleSheet(get_theme_stylesheet(applied_mode))
        if hasattr(self, "merged_text_edit"):
            self.merged_text_edit.line_number_area.update()
        if hasattr(self, "paste_text_edit"):
            self.paste_text_edit.line_number_area.update()

    def _reset_to_default_settings(self):
        self.mode_combo.setCurrentIndex(0)
        self.max_chars_spin.setValue(pytotext2.DEFAULT_MAX_CHARS)
        self.parts_spin.setValue(pytotext2.DEFAULT_NUM_PARTS)
        self.custom_pattern_input.clear()
        self.chk_ai_prompt.setChecked(True)
        self.ai_prompt_edit.setPlainText('Just say "I understood". I will share the prompt later.')
        self.chk_part_header.setChecked(True)
        self.chk_part_footer.setChecked(False)
        self.footer_edit.setPlainText("--- End of Part {part} of {total_parts} ---")
        self.statusBar().showMessage("Reset configuration to default settings.", 3000)

    # --------------------------------------------------
    # Dynamic Workflow State & Button Management
    # --------------------------------------------------
    def _update_workflow_state(self):
        has_selection = len(self.selected_files) > 0
        has_merged_text = len(self.merged_text_edit.toPlainText().strip()) > 0
        has_parts = len(self.output_parts) > 0

        self.btn_merge.setObjectName("")
        self.btn_split.setObjectName("")
        self.btn_export.setObjectName("")

        if not has_merged_text:
            self.btn_merge.setObjectName("primaryActionBtn")
            self.btn_merge.setText("Merge into Viewer")
            self.btn_split.setEnabled(False)
            self.btn_export.setEnabled(False)
            self.copy_viewer_btn.setEnabled(False)
            self.save_viewer_btn.setEnabled(False)
            self.clear_viewer_btn.setEnabled(False)
            self.viewer_stack.setCurrentIndex(0)
        elif not has_parts:
            self.btn_merge.setText("Merge Again")
            self.btn_split.setObjectName("primaryActionBtn")
            self.btn_split.setText("Split into Parts")
            self.btn_split.setEnabled(True)
            self.btn_export.setEnabled(False)
            self.copy_viewer_btn.setEnabled(True)
            self.save_viewer_btn.setEnabled(True)
            self.clear_viewer_btn.setEnabled(True)
            self.viewer_stack.setCurrentIndex(1)
        else:
            self.btn_merge.setText("Merge Again")
            self.btn_split.setText("Split Again")
            self.btn_split.setEnabled(True)
            self.btn_export.setObjectName("primaryActionBtn")
            self.btn_export.setEnabled(True)
            self.copy_viewer_btn.setEnabled(True)
            self.save_viewer_btn.setEnabled(True)
            self.clear_viewer_btn.setEnabled(True)
            self.viewer_stack.setCurrentIndex(1)

        self.copy_all_btn.setEnabled(has_parts)
        self.clear_out_btn.setEnabled(has_parts)

        self.btn_tree.setEnabled(has_selection or (self.root_path is not None and bool(self.discovered_files)))

        self.btn_merge.style().unpolish(self.btn_merge)
        self.btn_merge.style().polish(self.btn_merge)
        self.btn_split.style().unpolish(self.btn_split)
        self.btn_split.style().polish(self.btn_split)
        self.btn_export.style().unpolish(self.btn_export)
        self.btn_export.style().polish(self.btn_export)

    # --------------------------------------------------
    # File Explorer & Table Operations
    # --------------------------------------------------
    def _select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose Folder", str(self.root_path) if self.root_path else ".")
        if folder:
            self._open_folder_path(Path(folder).resolve())

    def _open_folder_path(self, folder_path: Path):
        self.root_path = folder_path
        self._add_recent_folder(self.root_path)
        self.path_display_label.setText(self.root_path.name)
        self.path_display_label.setToolTip(str(self.root_path))
        self._scan_directory(self.root_path)

    def _add_recent_folder(self, folder_path: Path):
        path_str = str(folder_path)
        if path_str in self.recent_folders:
            self.recent_folders.remove(path_str)
        self.recent_folders.insert(0, path_str)
        self.recent_folders = self.recent_folders[:10]

        self.recent_menu.clear()
        for f in self.recent_folders:
            act = self.recent_menu.addAction(f)
            act.triggered.connect(lambda _, p=f: self._open_folder_path(Path(p)))

    def _reveal_current_folder(self):
        if not self.root_path or not self.root_path.exists():
            return
        if sys.platform == "darwin":
            os.system(f'open "{self.root_path}"')
        elif sys.platform == "win32":
            os.system(f'explorer "{self.root_path}"')
        else:
            os.system(f'xdg-open "{self.root_path}"')

    def _copy_current_folder_path(self):
        if self.root_path:
            QApplication.clipboard().setText(str(self.root_path))
            self.statusBar().showMessage("Copied directory path to clipboard!", 2500)

    def _scan_directory(self, root: Path):
        if not root or not root.exists():
            return

        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.terminate()

        self.status_state_label.setText("● Scanning...")
        self.status_state_label.setStyleSheet("color: #d29922; font-weight: bold;")
        self.status_msg_label.setText(f"Scanning directory: {root.name}...")

        self.scan_worker = FolderScanWorker(root)
        self.scan_worker.progress_signal.connect(lambda count: self.status_msg_label.setText(f"Discovered {count:,} supported files..."))
        self.scan_worker.finished_signal.connect(self._on_scan_worker_finished)
        self.scan_worker.error_signal.connect(self._on_worker_error)
        self.scan_worker.start()

    def _on_scan_worker_finished(self, discovered: Dict[str, Path]):
        self.discovered_files = discovered
        self.file_char_map.clear()
        self._populate_file_tree()
        f_word = "file" if len(self.discovered_files) == 1 else "files"
        self.discovery_stats_label.setText(f"{len(self.discovered_files):,} {f_word} discovered")
        self.status_state_label.setText("● Ready")
        self.status_state_label.setStyleSheet("color: #2da44e; font-weight: bold;")
        self.status_msg_label.setText(f"Discovered {len(self.discovered_files):,} supported {f_word}.")
        self._update_workflow_state()

    # --------------------------------------------------
    # Tree population helpers
    # --------------------------------------------------

    def _build_tree_dict(self) -> dict:
        """Build a nested dict from flat discovered_files: {seg: {... or '__files__': [rel_path, ...]}}."""
        tree: dict = {}
        for rel_path in self.discovered_files:
            parts = rel_path.replace("\\", "/").split("/")
            node = tree
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node.setdefault("__files__", []).append(rel_path)
        return tree

    def _make_file_item(self, rel_path: str) -> QTreeWidgetItem:
        """Create a QTreeWidgetItem leaf for a single file."""
        abs_path = self.discovered_files[rel_path]
        filename = Path(rel_path).name
        override_badge = " ⚙" if (rel_path in self.cell_selection_map and self.cell_selection_map[rel_path] is not None) else ""
        display_name = f"{filename}{override_badge}"

        item = QTreeWidgetItem()
        item.setText(0, display_name)
        item.setData(0, Qt.ItemDataRole.UserRole, rel_path)       # rel_path key
        item.setData(0, Qt.ItemDataRole.UserRole + 1, "file")     # node type
        item.setToolTip(0, f"Full path:\n{abs_path}\n\nRelative path:\n{rel_path}\n(Double-click to configure cells, right-click for options)")

        # Checkbox on the file item itself
        is_checked = rel_path in self.selected_files
        item.setCheckState(0, Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

        # Size
        try:
            size_bytes = abs_path.stat().st_size
            size_str = f"{size_bytes / 1024:.1f} KB" if size_bytes >= 1024 else f"{size_bytes} B"
        except Exception:
            size_bytes = -1
            size_str = "N/A"
        item.setText(1, size_str)
        item.setData(1, Qt.ItemDataRole.UserRole, size_bytes)

        # Chars / Tokens
        chars_val = self.file_char_map.get(rel_path)
        if chars_val is not None:
            tok_cnt = chars_val // 4
            item.setText(2, f"{chars_val:,}")
            item.setData(2, Qt.ItemDataRole.UserRole, chars_val)
            tok_str = f"{tok_cnt / 1000:.1f}k" if tok_cnt >= 1000 else f"{tok_cnt}"
            item.setText(3, tok_str)
            item.setData(3, Qt.ItemDataRole.UserRole, tok_cnt)
            item.setToolTip(3, f"{tok_cnt:,} estimated tokens ({chars_val:,} chars)")
        else:
            item.setText(2, "--")
            item.setData(2, Qt.ItemDataRole.UserRole, -1)
            item.setText(3, "--")
            item.setData(3, Qt.ItemDataRole.UserRole, -1)

        return item

    def _make_folder_item(self, name: str) -> QTreeWidgetItem:
        """Create a QTreeWidgetItem folder node."""
        item = QTreeWidgetItem()
        item.setText(0, name)
        item.setData(0, Qt.ItemDataRole.UserRole + 1, "folder")
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsAutoTristate)
        item.setCheckState(0, Qt.CheckState.Unchecked)
        return item

    def _populate_tree_node(self, parent_item, subtree: dict):
        """Recursively add folder + file children to parent_item."""
        # Add sub-folders first (alphabetically), then files
        folder_keys = sorted(k for k in subtree if k != "__files__")
        for folder_name in folder_keys:
            folder_item = self._make_folder_item(folder_name)
            parent_item.addChild(folder_item)
            self._populate_tree_node(folder_item, subtree[folder_name])

        for rel_path in sorted(subtree.get("__files__", [])):
            file_item = self._make_file_item(rel_path)
            parent_item.addChild(file_item)

    def _populate_file_tree(self):
        self.file_tree.blockSignals(True)
        self.file_tree.setUpdatesEnabled(False)
        self.file_tree.clear()

        tree_dict = self._build_tree_dict()

        # Top-level: folders first, then root-level files
        folder_keys = sorted(k for k in tree_dict if k != "__files__")
        for folder_name in folder_keys:
            folder_item = self._make_folder_item(folder_name)
            self.file_tree.addTopLevelItem(folder_item)
            self._populate_tree_node(folder_item, tree_dict[folder_name])
            folder_item.setExpanded(True)  # Expand top-level folders by default

        for rel_path in sorted(tree_dict.get("__files__", [])):
            file_item = self._make_file_item(rel_path)
            self.file_tree.addTopLevelItem(file_item)

        self.file_tree.setUpdatesEnabled(True)
        self.file_tree.blockSignals(False)
        self._update_selection_stats()

    # --------------------------------------------------
    # Tree item signals
    # --------------------------------------------------

    def _on_tree_item_changed(self, item: QTreeWidgetItem, column: int):
        if column != 0:
            return
        node_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if node_type == "file":
            rel_path = item.data(0, Qt.ItemDataRole.UserRole)
            if rel_path:
                if item.checkState(0) == Qt.CheckState.Checked:
                    self.selected_files.add(rel_path)
                else:
                    self.selected_files.discard(rel_path)
        # For folder nodes Qt's ItemIsAutoTristate handles child propagation;
        # we sync selected_files by walking all file descendants
        elif node_type == "folder":
            self._sync_selected_files_from_tree()
        self._update_selection_stats()
        self._update_workflow_state()

    def _sync_selected_files_from_tree(self):
        """Walk all tree file items and rebuild selected_files from their check state."""
        self.selected_files.clear()
        it = QTreeWidgetItemIterator(self.file_tree)
        while it.value():
            item = it.value()
            if item.data(0, Qt.ItemDataRole.UserRole + 1) == "file":
                if item.checkState(0) == Qt.CheckState.Checked:
                    rel = item.data(0, Qt.ItemDataRole.UserRole)
                    if rel:
                        self.selected_files.add(rel)
            it += 1

    def _on_tree_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        node_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if node_type == "folder":
            item.setExpanded(not item.isExpanded())
        elif node_type == "file":
            rel_path = item.data(0, Qt.ItemDataRole.UserRole)
            if rel_path:
                abs_path = self.discovered_files.get(rel_path)
                if abs_path and (pytotext2.is_py_file(abs_path) or pytotext2.is_notebook_file(abs_path) or is_md_file(abs_path)):
                    self._configure_cells(rel_path, item)

    def _show_file_tree_context_menu(self, pos: QPoint):
        item = self.file_tree.itemAt(pos)
        if not item:
            return
        node_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
        menu = QMenu(self)

        if node_type == "folder":
            sel_folder_act = menu.addAction("Select All Files in Folder")
            sel_folder_act.triggered.connect(lambda: self._set_folder_check_state(item, Qt.CheckState.Checked))
            desel_folder_act = menu.addAction("Deselect All Files in Folder")
            desel_folder_act.triggered.connect(lambda: self._set_folder_check_state(item, Qt.CheckState.Unchecked))
            menu.exec(self.file_tree.viewport().mapToGlobal(pos))
            return

        if node_type == "file":
            rel_path = item.data(0, Qt.ItemDataRole.UserRole)
            abs_path = self.discovered_files.get(rel_path) if rel_path else None
            if not abs_path:
                return

            cfg_cells_act = menu.addAction("Configure Cell Exports…")
            cfg_cells_act.triggered.connect(lambda: self._configure_cells(rel_path, item))
            menu.addSeparator()

            open_file_act = menu.addAction("Open File in Default App")
            open_file_act.triggered.connect(lambda: self._open_external_file(abs_path))

            reveal_file_act = menu.addAction("Reveal in Finder / Explorer")
            reveal_file_act.triggered.connect(lambda: self._reveal_external_file(abs_path))

            copy_rel_act = menu.addAction("Copy Relative Path")
            copy_rel_act.triggered.connect(lambda: QApplication.clipboard().setText(rel_path))

            copy_abs_act = menu.addAction("Copy Absolute Path")
            copy_abs_act.triggered.connect(lambda: QApplication.clipboard().setText(str(abs_path)))

            menu.addSeparator()
            select_only_act = menu.addAction("Select Only This File")
            select_only_act.triggered.connect(lambda: self._select_only_single_file(rel_path))

            menu.exec(self.file_tree.viewport().mapToGlobal(pos))

    def _set_folder_check_state(self, folder_item: QTreeWidgetItem, state: Qt.CheckState):
        """Set all file descendants of a folder item to the given check state."""
        self.file_tree.blockSignals(True)
        folder_item.setCheckState(0, state)
        self.file_tree.blockSignals(False)
        # ItemIsAutoTristate propagates to children automatically when signals unblocked;
        # but we force it by walking manually for immediate sync
        self._walk_set_files(folder_item, state)
        self._sync_selected_files_from_tree()
        self._update_selection_stats()
        self._update_workflow_state()

    def _walk_set_files(self, item: QTreeWidgetItem, state: Qt.CheckState):
        """Recursively set all file leaf items under item to state (no signal)."""
        self.file_tree.blockSignals(True)
        for i in range(item.childCount()):
            child = item.child(i)
            child_type = child.data(0, Qt.ItemDataRole.UserRole + 1)
            if child_type == "file":
                child.setCheckState(0, state)
            elif child_type == "folder":
                self._walk_set_files(child, state)
        self.file_tree.blockSignals(False)

    def _open_external_file(self, path: Path):
        if sys.platform == "darwin":
            os.system(f'open "{path}"')
        elif sys.platform == "win32":
            os.system(f'start "" "{path}"')
        else:
            os.system(f'xdg-open "{path}"')

    def _reveal_external_file(self, path: Path):
        if sys.platform == "darwin":
            os.system(f'open -R "{path}"')
        elif sys.platform == "win32":
            os.system(f'explorer /select,"{path}"')
        else:
            os.system(f'xdg-open "{path.parent}"')

    def _select_only_single_file(self, target_rel: str):
        self.file_tree.blockSignals(True)
        self.selected_files.clear()
        it = QTreeWidgetItemIterator(self.file_tree)
        while it.value():
            item = it.value()
            if item.data(0, Qt.ItemDataRole.UserRole + 1) == "file":
                rel = item.data(0, Qt.ItemDataRole.UserRole)
                is_target = rel == target_rel
                item.setCheckState(0, Qt.CheckState.Checked if is_target else Qt.CheckState.Unchecked)
                if is_target:
                    self.selected_files.add(target_rel)
            it += 1
        self.file_tree.blockSignals(False)
        self._update_selection_stats()
        self._update_workflow_state()

    def _filter_file_tree(self, _=""):
        query = self.search_input.text().strip().lower()
        preset_idx = self.category_combo.currentIndex()

        CODE_EXTS = {".py", ".js", ".ts", ".c", ".cpp", ".h", ".hpp", ".sh", ".bash", ".rs", ".go", ".java"}
        DOC_EXTS = {".csv", ".txt", ".md", ".markdown", ".json", ".yaml", ".yml", ".sql", ".xml", ".html", ".css"}

        def file_matches(rel_path: str) -> bool:
            path_lower = rel_path.lower()
            if query and query not in path_lower:
                return False
            ext = Path(rel_path).suffix.lower()
            if preset_idx == 1:
                return ext in CODE_EXTS
            elif preset_idx == 2:
                return ext in DOC_EXTS
            elif preset_idx == 3:
                return ext == ".ipynb"
            return True

        def apply_to_item(item: QTreeWidgetItem) -> bool:
            """Returns True if this item or any descendant should be visible."""
            node_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if node_type == "file":
                rel_path = item.data(0, Qt.ItemDataRole.UserRole) or ""
                visible = file_matches(rel_path)
                item.setHidden(not visible)
                return visible
            # folder
            any_visible = False
            for i in range(item.childCount()):
                child_visible = apply_to_item(item.child(i))
                any_visible = any_visible or child_visible
            item.setHidden(not any_visible)
            if any_visible and (query or preset_idx > 0):
                item.setExpanded(True)
            return any_visible

        root = self.file_tree.invisibleRootItem()
        for i in range(root.childCount()):
            apply_to_item(root.child(i))

    def _apply_preset_filter(self, _):
        self._filter_file_tree()

    def _select_all_files(self):
        self.file_tree.blockSignals(True)
        it = QTreeWidgetItemIterator(self.file_tree)
        while it.value():
            item = it.value()
            if item.data(0, Qt.ItemDataRole.UserRole + 1) == "file" and not item.isHidden():
                item.setCheckState(0, Qt.CheckState.Checked)
                rel = item.data(0, Qt.ItemDataRole.UserRole)
                if rel:
                    self.selected_files.add(rel)
            it += 1
        self.file_tree.blockSignals(False)
        self._update_selection_stats()
        self._update_workflow_state()

    def _clear_file_selection(self):
        self.file_tree.blockSignals(True)
        self.selected_files.clear()
        it = QTreeWidgetItemIterator(self.file_tree)
        while it.value():
            item = it.value()
            if item.data(0, Qt.ItemDataRole.UserRole + 1) == "file":
                item.setCheckState(0, Qt.CheckState.Unchecked)
            it += 1
        self.file_tree.blockSignals(False)
        self._update_selection_stats()
        self._update_workflow_state()

    def _update_selection_stats(self):
        count = len(self.selected_files)
        f_word = "file" if count == 1 else "files"
        self.selection_stats_label.setText(f"{count} {f_word} selected")

        total_bytes = 0
        for rel in self.selected_files:
            abs_p = self.discovered_files.get(rel)
            if abs_p and abs_p.exists():
                try:
                    total_bytes += abs_p.stat().st_size
                except Exception:
                    pass

        size_str = f"{total_bytes / 1024:.1f} KB" if total_bytes >= 1024 else f"{total_bytes} B"

        merged_text = self.merged_text_edit.toPlainText() if hasattr(self, "merged_text_edit") else ""
        merged_chars = len(merged_text)
        merged_tokens = merged_chars // 4
        self.status_metrics_label.setText(
            f"Selected: {count} {f_word} ({size_str}) | Merged: {merged_chars:,} chars · ~{merged_tokens:,} tokens"
        )

    def _calculate_file_char_sizes(self):
        if not self.discovered_files:
            return

        self.status_state_label.setText("● Calculating...")
        self.status_state_label.setStyleSheet("color: #d29922; font-weight: bold;")
        self.status_msg_label.setText("Calculating file character and token counts on-demand...")

        self.char_worker = FolderCharCountWorker(self.discovered_files)
        self.char_worker.finished_signal.connect(self._on_char_worker_finished)
        self.char_worker.error_signal.connect(self._on_worker_error)
        self.char_worker.start()

    def _on_char_worker_finished(self, char_map: dict, total_chars: int, total_tokens: int):
        self.file_char_map = char_map
        it = QTreeWidgetItemIterator(self.file_tree)
        while it.value():
            item = it.value()
            if item.data(0, Qt.ItemDataRole.UserRole + 1) == "file":
                rel = item.data(0, Qt.ItemDataRole.UserRole)
                if rel and rel in char_map:
                    chars = char_map[rel]
                    tokens = chars // 4
                    tok_str = f"{tokens / 1000:.1f}k" if tokens >= 1000 else f"{tokens}"
                    item.setText(2, f"{chars:,}")
                    item.setData(2, Qt.ItemDataRole.UserRole, chars)
                    item.setText(3, tok_str)
                    item.setData(3, Qt.ItemDataRole.UserRole, tokens)
                    item.setToolTip(3, f"{tokens:,} estimated tokens ({chars:,} chars)")
            it += 1

        self.status_state_label.setText("● Ready")
        self.status_state_label.setStyleSheet("color: #2da44e; font-weight: bold;")
        f_count = len(char_map)
        f_word = "file" if f_count == 1 else "files"
        self.status_msg_label.setText(f"Calculated sizes for {f_count} {f_word}: Total {total_chars:,} chars (~{total_tokens:,} tokens).")
        self._update_selection_stats()

    def _configure_cells(self, rel_path: str, item: QTreeWidgetItem):
        abs_path = self.discovered_files[rel_path]
        try:
            if is_md_file(abs_path):
                cells = parse_md_cells(abs_path)
            elif pytotext2.is_notebook_file(abs_path):
                cells = pytotext2.notebook_cells(abs_path)
                cells = [{"cell_label": str(i), "cell_type": str(c.get("cell_type", "unknown")), "source": c.get("source", "")} for i, c in enumerate(cells, start=1)]
            else:
                cells = parse_py_cells_unified(abs_path)
        except Exception as e:
            QMessageBox.critical(self, "Cell Error", f"Could not parse cells for {rel_path}:\n{e}")
            return

        dialog = QDialogCellPicker(rel_path, cells, self.cell_selection_map.get(rel_path), parent=self)
        if dialog.exec():
            selection = dialog.get_selection()
            self.cell_selection_map[rel_path] = selection
            override_badge = " ⚙" if selection is not None else ""
            filename = Path(rel_path).name
            item.setText(0, f"{filename}{override_badge}")

    # --------------------------------------------------
    # Configuration Deck Helpers
    # --------------------------------------------------
    def _on_split_mode_changed(self, index: int):
        if index == 0:  # Max Chars / Part
            self.budget_label.setText("Limit:")
            self.max_chars_spin.show()
            self.max_chars_spin.setValue(pytotext2.DEFAULT_MAX_CHARS)
            self.max_chars_spin.setSingleStep(5000)
            self.parts_spin.hide()
        elif index == 1:  # Max Tokens / Part
            self.budget_label.setText("Tokens:")
            self.max_chars_spin.show()
            self.max_chars_spin.setValue(30000)
            self.max_chars_spin.setSingleStep(1000)
            self.parts_spin.hide()
        else:  # Fixed N Parts
            self.budget_label.setText("Parts:")
            self.max_chars_spin.hide()
            self.parts_spin.show()

    def _update_ai_prompt_counter(self):
        txt = self.ai_prompt_edit.toPlainText()
        chars = len(txt)
        tokens = chars // 4
        self.ai_prompt_count_label.setText(f"{chars} chars · ~{tokens} tokens")

    def _update_paste_stats(self):
        txt = self.paste_text_edit.toPlainText()
        chars = len(txt)
        tokens = chars // 4
        self.paste_stats_label.setText(f"{chars:,} chars · ~{tokens:,} tokens")
        # Show/hide Render Jupyter button based on marker detection
        if hasattr(self, "render_jupyter_btn"):
            show = bool(txt.strip()) and has_jupyter_markers(txt)
            self.render_jupyter_btn.setVisible(show)

    def _render_jupyter_view(self):
        """Parse pasted text into cells and switch to Jupyter notebook view."""
        txt = self.paste_text_edit.toPlainText()
        if not txt.strip():
            return

        # Determine parser: if fenced code blocks present, use fenced parser;
        # otherwise use the unified cell parser
        has_fenced = any(FENCED_CODE_OPEN_RE.match(line.strip()) for line in txt.splitlines() if line.strip())

        if has_fenced:
            cells = parse_fenced_code_cells(txt)
        else:
            cells = parse_unified_cells(txt)

        if not cells:
            return

        # Remove old notebook view if any
        old_widget = self.paste_stack.widget(1)
        if old_widget:
            self.paste_stack.removeWidget(old_widget)
            old_widget.deleteLater()

        # Create and insert new notebook view
        notebook_view = JupiterNotebookView(cells)
        notebook_view.back_to_editor_signal.connect(self._back_to_editor)
        self.paste_stack.insertWidget(1, notebook_view)
        self.paste_stack.setCurrentIndex(1)

    def _back_to_editor(self, reconstructed_text: str):
        """Switch from Jupyter view back to raw text editor."""
        self.paste_text_edit.setPlainText(reconstructed_text)
        self.paste_stack.setCurrentIndex(0)

    # --------------------------------------------------
    # Workflow Operations: Merge, Tree, Split, Export
    # --------------------------------------------------
    def _merge_selected_files_to_viewer(self):
        if self.sidebar_tabs.currentIndex() == 1:
            paste_txt = self.paste_text_edit.toPlainText()
            if paste_txt.strip():
                self.merged_text_edit.setPlainText(paste_txt)
                self.viewer_title_label.setText("<b>Merged Text Viewer</b> (Pasted Buffer)")
                self.status_msg_label.setText("Loaded paste buffer into viewer.")
                self._update_viewer_stats()
                self._update_workflow_state()
                return

        valid_selected = [rel for rel in sorted(list(self.selected_files)) if rel in self.discovered_files]
        if not valid_selected:
            QMessageBox.warning(self, "No Selection", "Please select at least one file from the file explorer.")
            return

        self.status_state_label.setText("● Merging...")
        self.status_state_label.setStyleSheet("color: #d29922; font-weight: bold;")
        f_word = "file" if len(valid_selected) == 1 else "files"
        self.status_msg_label.setText(f"Merging {len(valid_selected)} {f_word} asynchronously...")

        self.merge_worker = FolderMergeWorker(
            selected_files=valid_selected,
            discovered_files=self.discovered_files,
            cell_map=self.cell_selection_map,
            cell_format="plain",
        )
        self.merge_worker.finished_signal.connect(self._on_merge_worker_finished)
        self.merge_worker.error_signal.connect(self._on_worker_error)
        self.merge_worker.start()

    def _on_merge_worker_finished(self, merged_text: str, file_count: int):
        self.merged_text_edit.setPlainText(merged_text)
        f_word = "file" if file_count == 1 else "files"
        self.viewer_title_label.setText(f"<b>Merged Text Viewer</b> ({file_count} {f_word} merged)")
        self.status_state_label.setText("● Ready")
        self.status_state_label.setStyleSheet("color: #2da44e; font-weight: bold;")
        self.status_msg_label.setText(f"Successfully merged {file_count} {f_word} into viewer!")
        self._update_viewer_stats()
        self._update_workflow_state()

    def _clear_merged_viewer(self):
        self.merged_text_edit.clear()
        self.viewer_title_label.setText("<b>Merged Text Viewer</b>")
        self._update_viewer_stats()
        self._update_workflow_state()

    def _insert_folder_tree_into_viewer(self):
        if not self.root_path or not self.discovered_files:
            QMessageBox.warning(self, "No Folder", "Please open a folder first.")
            return

        valid_selected = [rel for rel in sorted(list(self.selected_files)) if rel in self.discovered_files]
        selected_paths = [self.discovered_files[rel] for rel in valid_selected] if valid_selected else list(self.discovered_files.values())
        formatted_tree = generate_folder_tree(self.root_path, selected_paths) + "\n\n"

        current_text = self.merged_text_edit.toPlainText()
        self.merged_text_edit.setPlainText(formatted_tree + current_text)
        self.status_msg_label.setText("Inserted folder tree hierarchy into viewer!")
        self._update_viewer_stats()
        self._update_workflow_state()

    def _split_merged_viewer_text(self):
        text = self.merged_text_edit.toPlainText()
        if not text.strip():
            text = self.paste_text_edit.toPlainText()
            if not text.strip():
                QMessageBox.warning(self, "Empty Content", "No merged text or paste content available to split.")
                return

        mode_idx = self.mode_combo.currentIndex()
        if mode_idx == 0:
            mode = "maxchars"
        elif mode_idx == 1:
            mode = "maxtokens"
        else:
            mode = "fixedparts"

        limit_val = self.max_chars_spin.value()
        num_parts = self.parts_spin.value()
        custom_pattern = self.custom_pattern_input.text().strip()
        include_header = self.chk_part_header.isChecked()
        prepend_ai_prompt = self.chk_ai_prompt.isChecked()
        ai_prompt_text = self.ai_prompt_edit.toPlainText()
        append_footer = self.chk_part_footer.isChecked()
        footer_text = self.footer_edit.toPlainText()

        self._hide_stop_button()
        self.split_timer.start(10000)

        self.status_state_label.setText("● Splitting...")
        self.status_state_label.setStyleSheet("color: #d29922; font-weight: bold;")
        self.status_msg_label.setText("Splitting text into balanced parts...")

        self.process_worker = TextProcessWorker(
            mode=mode,
            text_buffer=text,
            limit_value=limit_val,
            num_parts=num_parts,
            cell_format="plain",
            coefficients_str=custom_pattern,
            include_header=include_header,
            prepend_ai_prompt=prepend_ai_prompt,
            ai_prompt_text=ai_prompt_text,
            append_footer=append_footer,
            footer_text=footer_text,
        )
        self.process_worker.finished_signal.connect(self._on_text_process_finished)
        self.process_worker.cancelled_signal.connect(self._on_split_cancelled)
        self.process_worker.error_signal.connect(self._on_worker_error)
        self.process_worker.start()

    def _on_text_process_finished(self, parts: List[str], _):
        self._hide_stop_button()
        self.display_output_parts(parts)
        self.status_state_label.setText("● Ready")
        self.status_state_label.setStyleSheet("color: #2da44e; font-weight: bold;")
        p_word = "part" if len(parts) == 1 else "parts"
        self.status_msg_label.setText(f"Created {len(parts)} balanced output {p_word}.")
        self._update_workflow_state()
        self._save_config_session()

    def _show_stop_button(self):
        self.stop_op_btn.show()
        self.status_msg_label.setText("Processing taking >10 seconds... Click 'Stop' to cancel.")

    def _hide_stop_button(self):
        self.split_timer.stop()
        self.stop_op_btn.hide()

    def _cancel_split_operation(self):
        if self.process_worker and self.process_worker.isRunning():
            self.process_worker.cancel()
            self.status_msg_label.setText("Cancelling operation...")

    def _on_split_cancelled(self):
        self._hide_stop_button()
        self.status_state_label.setText("● Ready")
        self.status_state_label.setStyleSheet("color: #2da44e; font-weight: bold;")
        self.status_msg_label.setText("Operation cancelled.")
        self._update_workflow_state()

    def _on_worker_error(self, err_msg: str):
        self._hide_stop_button()
        self.status_state_label.setText("● Error")
        self.status_state_label.setStyleSheet("color: #cf222e; font-weight: bold;")
        self.status_msg_label.setText("Operation failed.")
        QMessageBox.critical(self, "Error", f"Operation failed:\n{err_msg}")
        self._update_workflow_state()

    # --------------------------------------------------
    # Split Output Parts Inspector & Rich Tab Cards
    # --------------------------------------------------
    def _clear_output_parts(self):
        self.output_parts.clear()
        self.output_tabs.clear()
        self.output_stack.setCurrentIndex(0)
        self.total_output_stats_label.setText("0 parts · 0 chars · 0 tokens")
        self._update_workflow_state()

    def display_output_parts(self, parts: List[str]):
        self.output_parts = parts
        self.output_tabs.clear()

        total_chars = sum(len(p) for p in parts)
        est_tokens = total_chars // 4
        p_word = "part" if len(parts) == 1 else "parts"
        self.total_output_stats_label.setText(f"{len(parts)} {p_word} · {total_chars:,} chars · ~{est_tokens:,} tokens")

        if not parts:
            self._clear_output_parts()
            return

        self.output_stack.setCurrentIndex(1)
        mode_idx = self.mode_combo.currentIndex()
        if mode_idx == 0:
            budget = self.max_chars_spin.value()
        elif mode_idx == 1:
            budget = self.max_chars_spin.value() * 4
        else:
            budget = total_chars // max(1, len(parts))

        for idx, part_content in enumerate(parts, start=1):
            tab = self._create_single_part_card(idx, len(parts), part_content, budget)
            self.output_tabs.addTab(tab, f"Part {idx} ({len(part_content):,} chars)")

    def _create_single_part_card(self, part_num: int, total_parts: int, content: str, budget: int) -> QWidget:
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        header = QHBoxLayout()
        chars = len(content)
        tokens = chars // 4
        pct = min(200, int((chars / max(1, budget)) * 100)) if budget > 0 else 100

        if pct <= 85:
            pct_color = "#2da44e"
        elif pct <= 95:
            pct_color = "#d29922"
        elif pct <= 100:
            pct_color = "#bf8700"
        else:
            pct_color = "#cf222e"

        stats_lbl = QLabel(f"<b>Part {part_num} of {total_parts}</b> · {chars:,} chars · ~{tokens:,} tokens")
        header.addWidget(stats_lbl)

        gauge_lbl = QLabel(f"<b>{pct}%</b> limit")
        gauge_lbl.setStyleSheet(f"background-color: {pct_color}22; color: {pct_color}; border: 1px solid {pct_color}55; border-radius: 4px; padding: 2px 6px; font-weight: bold;")
        header.addWidget(gauge_lbl)

        header.addStretch()

        if part_num < total_parts:
            next_btn = QPushButton(f"Copy & Next ➔ (Part {part_num + 1})")
            next_btn.setObjectName("accentBtn")
            next_btn.clicked.connect(lambda _, c=content, b=next_btn, idx=part_num: self._copy_and_switch_next(c, b, idx))
            header.addWidget(next_btn)

        copy_btn = QPushButton("Copy Part")
        copy_btn.clicked.connect(lambda _, c=content, b=copy_btn: self._copy_to_clipboard(c, b))
        header.addWidget(copy_btn)

        export_part_btn = QPushButton("Export Part…")
        export_part_btn.clicked.connect(lambda _, c=content, idx=part_num: self._export_single_part(c, idx))
        header.addWidget(export_part_btn)

        layout.addLayout(header)

        text_edit = CodeEditorWithLineNumbers()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(content)
        layout.addWidget(text_edit, 1)

        return tab_widget

    def _copy_and_switch_next(self, text: str, button: QPushButton, current_index: int):
        QApplication.clipboard().setText(text)
        button.setText("✓ Copied!")
        QApplication.processEvents()
        QThread.msleep(150)
        button.setText(f"Copy & Next ➔ (Part {current_index + 1})")
        self.statusBar().showMessage(f"Copied Part {current_index} to clipboard! Switched to Part {current_index + 1}.", 2500)
        if current_index < self.output_tabs.count():
            self.output_tabs.setCurrentIndex(current_index)

    def _copy_to_clipboard(self, text: str, button: QPushButton):
        QApplication.clipboard().setText(text)
        orig_text = button.text()
        button.setText("✓ Copied!")
        QApplication.processEvents()
        QThread.msleep(150)
        button.setText(orig_text)
        self.statusBar().showMessage("Copied to clipboard!", 2500)

    def _copy_all_parts(self):
        if not self.output_parts:
            return
        combined_text = "\n\n" + ("=" * 40) + "\n\n".join(
            f"--- PART {i+1} ---\n{part}" for i, part in enumerate(self.output_parts)
        )
        QApplication.clipboard().setText(combined_text)
        self.statusBar().showMessage("Copied ALL parts with section delimiters to clipboard!", 3000)

    def _save_merged_viewer_file(self):
        text = self.merged_text_edit.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, "Empty Viewer", "Merged text viewer is empty.")
            return

        filters = (
            "Python Files (*.py);;"
            "Markdown Files (*.md *.markdown);;"
            "Text Files (*.txt);;"
            "JSON Files (*.json);;"
            "YAML Files (*.yaml *.yml);;"
            "HTML/CSS/JS (*.html *.css *.js *.ts);;"
            "All Files (*)"
        )
        default_dir = str(self.root_path / "merged_output.txt") if self.root_path else "merged_output.txt"
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save Merged Text As",
            default_dir,
            filters,
            "Text Files (*.txt)"
        )
        if file_path:
            try:
                Path(file_path).write_text(text, encoding="utf-8")
                self.statusBar().showMessage(f"Saved merged text to: {file_path}", 3500)
                QMessageBox.information(self, "Saved Successfully", f"Merged text saved to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save file:\n{e}")

    def _export_single_part(self, content: str, part_num: int):
        default_name = f"combined_part_{part_num}.txt"
        filters = (
            "Text Files (*.txt);;"
            "Python Files (*.py);;"
            "Markdown Files (*.md *.markdown);;"
            "JSON Files (*.json);;"
            "All Files (*)"
        )
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export Part {part_num}",
            default_name,
            filters,
            "Text Files (*.txt)"
        )
        if file_path:
            try:
                Path(file_path).write_text(content, encoding="utf-8")
                self.statusBar().showMessage(f"Saved Part {part_num} to: {file_path}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save part:\n{e}")

    def _save_active_part_or_viewer(self):
        # If split parts are open and active tab exists, export active tab part
        if self.output_parts and hasattr(self, "output_tabs") and self.output_stack.currentIndex() == 1:
            idx = self.output_tabs.currentIndex()
            if 0 <= idx < len(self.output_parts):
                self._export_single_part(self.output_parts[idx], idx + 1)
                return
        # Otherwise save merged viewer text
        self._save_merged_viewer_file()

    def _copy_active_part_or_viewer(self):
        if self.output_parts and hasattr(self, "output_tabs") and self.output_stack.currentIndex() == 1:
            idx = self.output_tabs.currentIndex()
            if 0 <= idx < len(self.output_parts):
                QApplication.clipboard().setText(self.output_parts[idx])
                self.statusBar().showMessage(f"Copied Part {idx + 1} to clipboard!", 2500)
                return
        text = self.merged_text_edit.toPlainText()
        if text.strip():
            QApplication.clipboard().setText(text)
            self.statusBar().showMessage("Copied merged viewer content to clipboard!", 2500)

    def _export_output_files(self):
        if not self.output_parts:
            QMessageBox.warning(self, "No Output", "No generated parts to export.")
            return

        prefix, ok = QInputDialog_getText(self, "Export Prefix", "Enter filename prefix:", "combined_part_")
        if not ok or not prefix:
            return

        folder = QFileDialog.getExistingDirectory(self, "Save Directory", str(self.root_path) if self.root_path else ".")
        if not folder:
            return

        save_dir = Path(folder)
        for i, part in enumerate(self.output_parts, start=1):
            file_path = save_dir / f"{prefix}{i}.txt"
            file_path.write_text(part, encoding="utf-8")

        f_word = "file" if len(self.output_parts) == 1 else "files"
        QMessageBox.information(self, "Export Complete", f"Successfully exported {len(self.output_parts)} {f_word} to:\n{save_dir}")

    # --------------------------------------------------
    # Merged Viewer Find & Replace Operations
    # --------------------------------------------------
    def _toggle_find_replace_bar(self):
        if self.find_replace_widget.isVisible():
            self.find_replace_widget.hide()
        else:
            self.find_replace_widget.show()
            self.find_input.setFocus()
            self.find_input.selectAll()
            self._on_find_text_changed()

    def _get_find_flags(self, backward: bool = False) -> QTextDocument.FindFlag:
        flags = QTextDocument.FindFlag(0)
        if backward:
            flags |= QTextDocument.FindFlag.FindBackward
        if self.chk_match_case.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        return flags

    def _on_find_text_changed(self):
        query = self.find_input.text()
        if not query:
            self.match_count_label.setText("0 matches")
            return
        text = self.merged_text_edit.toPlainText()
        count = text.count(query) if self.chk_match_case.isChecked() else text.lower().count(query.lower())
        self.match_count_label.setText(f"{count} match{'es' if count != 1 else ''}")

    def _find_next(self):
        query = self.find_input.text()
        if not query:
            return
        flags = self._get_find_flags(backward=False)
        found = self.merged_text_edit.find(query, flags)
        if not found:
            cursor = self.merged_text_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.merged_text_edit.setTextCursor(cursor)
            found = self.merged_text_edit.find(query, flags)
            if not found:
                self.statusBar().showMessage(f"Phrase '{query}' not found.", 2500)

    def _find_prev(self):
        query = self.find_input.text()
        if not query:
            return
        flags = self._get_find_flags(backward=True)
        found = self.merged_text_edit.find(query, flags)
        if not found:
            cursor = self.merged_text_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.merged_text_edit.setTextCursor(cursor)
            found = self.merged_text_edit.find(query, flags)
            if not found:
                self.statusBar().showMessage(f"Phrase '{query}' not found.", 2500)

    def _replace_next(self):
        query = self.find_input.text()
        replacement = self.replace_input.text()
        if not query:
            return
        cursor = self.merged_text_edit.textCursor()
        if cursor.hasSelection():
            selected_text = cursor.selectedText()
            match = (selected_text == query) if self.chk_match_case.isChecked() else (selected_text.lower() == query.lower())
            if match:
                cursor.insertText(replacement)
                self._find_next()
                self._on_find_text_changed()
                return
        self._find_next()
        cursor = self.merged_text_edit.textCursor()
        if cursor.hasSelection():
            cursor.insertText(replacement)
            self._find_next()
            self._on_find_text_changed()

    def _replace_all(self):
        query = self.find_input.text()
        replacement = self.replace_input.text()
        if not query:
            return
        text = self.merged_text_edit.toPlainText()
        if not self.chk_match_case.isChecked():
            import re
            pattern = re.compile(re.escape(query), re.IGNORECASE)
            new_text, count = pattern.subn(replacement, text)
        else:
            count = text.count(query)
            new_text = text.replace(query, replacement)

        if count > 0:
            self.merged_text_edit.setPlainText(new_text)
            self.statusBar().showMessage(f"Replaced {count} occurrence(s) successfully!", 3000)
            self._on_find_text_changed()
        else:
            self.statusBar().showMessage(f"No occurrences of '{query}' found.", 2500)

    def _update_viewer_stats(self):
        text = self.merged_text_edit.toPlainText()
        length = len(text)
        tokens = length // 4
        file_count = len(self.selected_files) if length > 0 else 0
        f_word = "file" if file_count == 1 else "files"
        self.viewer_stats_label.setText(f"{length:,} chars · ~{tokens:,} tokens · {file_count} {f_word} merged")
        self._update_selection_stats()
        self._update_workflow_state()

    # --------------------------------------------------
    # Configuration Session & JSON Persistence
    # --------------------------------------------------
    def _export_config_json(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export JSON Config", "pytotext_config.json", "JSON Files (*.json)")
        if file_path:
            self._save_config_file(Path(file_path))
            QMessageBox.information(self, "Config Saved", f"Configuration exported to:\n{file_path}")

    def _import_config_json(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Import JSON Config", "", "JSON Files (*.json)")
        if file_path:
            self._load_config_file(Path(file_path))
            QMessageBox.information(self, "Config Loaded", f"Configuration loaded from:\n{file_path}")

    def _save_config_session(self):
        self._save_config_file(CONFIG_FILE)

    def _load_config_session(self):
        if CONFIG_FILE.exists():
            self._load_config_file(CONFIG_FILE)

    def closeEvent(self, event):
        try:
            self._save_config_session()
        except Exception as e:
            print(f"Error saving session on exit: {e}")
        event.accept()

    # --------------------------------------------------
    # Update Management
    # --------------------------------------------------
    def _check_for_updates(self):
        self.update_btn.setEnabled(False)
        self.update_btn.setText("🔄 Checking...")
        self.statusBar().showMessage("Checking for updates from GitHub repository...", 5000)

        self._update_worker = UpdateCheckWorker(action="check")
        self._update_worker.check_finished.connect(self._on_update_check_finished)
        self._update_worker.start()

    def _on_update_check_finished(self, has_update: bool, local_rev: str, remote_rev: str, error_msg: str):
        self.update_btn.setEnabled(True)
        self.update_btn.setText("🔄 Check Updates")

        if error_msg == "LOCAL_NOT_GIT":
            short_remote = remote_rev[:7] if remote_rev else "latest"
            msg = (
                f"The application is running outside of a Git repository clone.\n\n"
                f"Latest remote commit on GitHub is: {short_remote}\n"
                f"Repository: https://github.com/serkanpaker/pytotext.git\n\n"
                f"To enable automatic updates, clone the project using Git:\n"
                f"git clone https://github.com/serkanpaker/pytotext.git"
            )
            QMessageBox.information(self, "Update Status", msg)
            self.statusBar().showMessage("Update check complete: not a git clone.", 4000)
            return

        if error_msg:
            QMessageBox.warning(self, "Update Check Error", f"Unable to check for updates:\n{error_msg}")
            self.statusBar().showMessage("Failed to check for updates.", 4000)
            return

        if has_update:
            short_local = local_rev[:7] if local_rev else "unknown"
            short_remote = remote_rev[:7] if remote_rev else "unknown"
            reply = QMessageBox.question(
                self,
                "Update Available",
                f"A new update is available on GitHub!\n\n"
                f"Current Local Version:  {short_local}\n"
                f"Latest Remote Version: {short_remote}\n"
                f"Repository: https://github.com/serkanpaker/pytotext.git\n\n"
                f"Would you like to pull the latest changes now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._pull_latest_updates()
        else:
            short_local = local_rev[:7] if local_rev else "HEAD"
            QMessageBox.information(
                self,
                "Up to Date",
                f"PyToText is up to date!\n\n"
                f"Current commit: {short_local}\n"
                f"Repository: https://github.com/serkanpaker/pytotext.git",
            )
            self.statusBar().showMessage("PyToText is up to date.", 4000)

    def _pull_latest_updates(self):
        self.update_btn.setEnabled(False)
        self.update_btn.setText("⬇ Updating...")
        self.statusBar().showMessage("Pulling latest updates from GitHub...", 8000)

        self._pull_worker = UpdateCheckWorker(action="pull")
        self._pull_worker.pull_finished.connect(self._on_pull_finished)
        self._pull_worker.start()

    def _on_pull_finished(self, success: bool, msg: str):
        self.update_btn.setEnabled(True)
        self.update_btn.setText("🔄 Check Updates")

        if success:
            QMessageBox.information(
                self,
                "Update Complete",
                f"PyToText was updated successfully!\n\n{msg}\n\nPlease restart the application to apply changes.",
            )
            self.statusBar().showMessage("Updated successfully. Restart app to apply.", 5000)
        else:
            QMessageBox.critical(
                self,
                "Update Failed",
                f"Could not pull updates from repository:\n\n{msg}\n\nPlease check your internet connection or git status.",
            )
            self.statusBar().showMessage("Update failed.", 5000)


    def _save_config_file(self, target_path: Path):
        data = {
            "mode": self.mode_combo.currentIndex(),
            "max_chars": self.max_chars_spin.value(),
            "num_parts": self.parts_spin.value(),
            "custom_pattern": self.custom_pattern_input.text().strip(),
            "include_part_header": self.chk_part_header.isChecked(),
            "prepend_ai_prompt": self.chk_ai_prompt.isChecked(),
            "ai_prompt_text": self.ai_prompt_edit.toPlainText(),
            "append_part_footer": self.chk_part_footer.isChecked(),
            "footer_text": self.footer_edit.toPlainText(),
            "theme_mode": self.current_theme_mode,
            "root_path": str(self.root_path) if self.root_path else "",
            "recent_folders": self.recent_folders,
            "selected_files": list(self.selected_files),
            "cell_selection_map": self.cell_selection_map,
            "saved_paste_buffer": self.paste_text_edit.toPlainText(),
            "saved_viewer_buffer": self.merged_text_edit.toPlainText(),
            "main_splitter_sizes": self.main_splitter.sizes(),
            "workspace_splitter_sizes": self.workspace_splitter.sizes(),
        }
        try:
            target_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"Could not save config: {e}")

    def _load_config_file(self, source_path: Path):
        try:
            data = json.loads(source_path.read_text(encoding="utf-8"))
            self.mode_combo.setCurrentIndex(data.get("mode", 0))
            self.max_chars_spin.setValue(data.get("max_chars", pytotext2.DEFAULT_MAX_CHARS))
            self.parts_spin.setValue(data.get("num_parts", pytotext2.DEFAULT_NUM_PARTS))
            self.custom_pattern_input.setText(data.get("custom_pattern", ""))

            self.chk_part_header.setChecked(data.get("include_part_header", True))
            self.chk_ai_prompt.setChecked(data.get("prepend_ai_prompt", True))
            self.ai_prompt_edit.setPlainText(data.get("ai_prompt_text", 'Just say "I understood". I will share the prompt later.'))
            self.chk_part_footer.setChecked(data.get("append_part_footer", False))
            self.footer_edit.setPlainText(data.get("footer_text", "--- End of Part {part} of {total_parts} ---"))

            theme_mode = data.get("theme_mode", data.get("theme", "system"))
            if theme_mode in ["system", "light", "dark"]:
                self.current_theme_mode = theme_mode
                t_idx = ["system", "light", "dark"].index(theme_mode)
                self.theme_combo.blockSignals(True)
                self.theme_combo.setCurrentIndex(t_idx)
                self.theme_combo.blockSignals(False)
                self._apply_theme()

            self.recent_folders = [f for f in data.get("recent_folders", []) if Path(f).exists()]
            self.recent_menu.clear()
            for f in self.recent_folders:
                act = self.recent_menu.addAction(f)
                act.triggered.connect(lambda _, p=f: self._open_folder_path(Path(p)))

            self.selected_files = set(data.get("selected_files", []))
            self.cell_selection_map = data.get("cell_selection_map", {})

            saved_paste = data.get("saved_paste_buffer", "")
            if saved_paste:
                self.paste_text_edit.setPlainText(saved_paste)

            saved_viewer = data.get("saved_viewer_buffer", "")
            if saved_viewer:
                self.merged_text_edit.setPlainText(saved_viewer)

            if "main_splitter_sizes" in data and len(data["main_splitter_sizes"]) == 2:
                self.main_splitter.setSizes(data["main_splitter_sizes"])

            if "workspace_splitter_sizes" in data and len(data["workspace_splitter_sizes"]) == 2:
                self.workspace_splitter.setSizes(data["workspace_splitter_sizes"])

            if data.get("root_path") and Path(data["root_path"]).exists():
                self._open_folder_path(Path(data["root_path"]).resolve())
        except Exception as e:
            print(f"Could not load config: {e}")


# --------------------------------------------------
# Interactive Cell Selection Dialog
# --------------------------------------------------
class QDialogCellPicker(QDialog):
    def __init__(self, rel_path: str, cells: List[dict], current_selection: Optional[List[str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Configure Cells — {rel_path}")
        self.resize(500, 360)
        self.cells = cells

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        layout.addWidget(QLabel(f"<b>Select cell(s) to export for:</b><br><span style='color:#7e8b9b;'>{rel_path}</span>"))

        self.radio_all = QRadioButton("Export ALL Cells")
        self.radio_custom = QRadioButton("Select Specific Cell(s)")

        if current_selection is None:
            self.radio_all.setChecked(True)
        else:
            self.radio_custom.setChecked(True)

        layout.addWidget(self.radio_all)
        layout.addWidget(self.radio_custom)

        self.cell_list = QTreeWidget()
        self.cell_list.setHeaderLabels(["✓", "Label", "Type", "Source Preview"])
        self.cell_list.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.cell_list.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.cell_list.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.cell_list.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.cell_list.setEnabled(current_selection is not None)
        self.radio_custom.toggled.connect(self.cell_list.setEnabled)

        current_norm = {pytotext2.normalize_cell_label(x) for x in current_selection} if current_selection else set()

        for idx, cell in enumerate(cells, start=1):
            lbl = str(cell.get("cell_label") or idx)
            c_type = str(cell.get("cell_type", "code")).lower()
            src = cell.get("source", "")
            if isinstance(src, list):
                src = "".join(str(s) for s in src)
            preview = " ".join(str(src).strip().split())
            if len(preview) > 60:
                preview = preview[:57] + "..."

            item = QTreeWidgetItem(self.cell_list, ["", lbl, c_type, preview or "(empty)"])
            is_checked = (current_selection is None) or (pytotext2.normalize_cell_label(lbl) in current_norm)
            item.setCheckState(0, Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)

        layout.addWidget(self.cell_list, 1)

        btn_box = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("primaryActionBtn")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_box.addStretch()
        btn_box.addWidget(ok_btn)
        btn_box.addWidget(cancel_btn)
        layout.addLayout(btn_box)

    def get_selection(self) -> Optional[List[str]]:
        if self.radio_all.isChecked():
            return None
        selected = []
        for i in range(self.cell_list.topLevelItemCount()):
            item = self.cell_list.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                selected.append(item.text(1))
        return selected


def QInputDialog_getText(parent, title: str, label: str, default: str) -> Tuple[str, bool]:
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.resize(340, 120)

    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel(label))

    line_edit = QLineEdit(default)
    layout.addWidget(line_edit)

    btn_box = QHBoxLayout()
    ok_btn = QPushButton("OK")
    ok_btn.setObjectName("primaryActionBtn")
    cancel_btn = QPushButton("Cancel")

    btn_box.addStretch()
    btn_box.addWidget(ok_btn)
    btn_box.addWidget(cancel_btn)
    layout.addLayout(btn_box)

    ok_btn.clicked.connect(dialog.accept)
    cancel_btn.clicked.connect(dialog.reject)

    res = dialog.exec()
    return line_edit.text(), res == QDialog.DialogCode.Accepted


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PyToText")
    app_icon = pytotext_assets.get_app_icon()
    if app_icon:
        app.setWindowIcon(app_icon)

    window = PyToTextMainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
