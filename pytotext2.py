#!/usr/bin/env python3
"""
pytotext2.py

Interactive exporter for .py and .ipynb files.

Features
--------
- Non-recursive folder navigation:
    ls, cd <subfolder>, back, pwd
- Select files interactively:
    add, remove, addall, clear, selected
- Exclude/include files without losing selection:
    exclude, include, excluded
- Supports:
    - .py files
    - .ipynb notebooks
- Notebook-like .py support:
    Detects cell markers such as:
        # %%
        # %% [code]
        # %% [markdown]
        Cell 1
        Cell 1:
        cell1
        cEll1
        CelL 1
        ...
- Cell helpers:
    nbinfo <file>          -> show cells if notebook or notebook-like .py
    cells <file> all       -> export all cells
    cells <file> 1,5,6     -> export only selected cells
    cells <file> 2,2b,12a  -> export explicit Python cell labels
    clearcells <file>      -> remove custom cell selection
    cellmap                -> show current per-file cell selection
- Output split modes:
    1) split by max chars per file
    2) split into exactly N parts

Notes
-----
- Notebook cells are 1-based.
- Notebook-like Python files preserve explicit labels such as `0`, `2b`, `11b`.
- This script skips itself from export candidates.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


DEFAULT_MAX_CHARS = 119_900
DEFAULT_NUM_PARTS = 5
OUT_SUFFIX = ".txt"
CHUNK_SIZE = 8_192
CELL_FORMAT_DIVIDER = "plain"
CELL_FORMAT_LABELED = "labeled"


# --------------------------------------------------
# Utilities
# --------------------------------------------------
def normalize_user_input(text: str) -> str:
    text = text.strip().strip('"').strip("'")
    text = text.replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    return text


def safe_relpath(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def read_text_best_effort(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


TEXT_EXTENSIONS = {
    ".py", ".ipynb", ".md", ".markdown", ".txt", ".csv", ".json", ".yaml", ".yml",
    ".html", ".css", ".js", ".ts", ".jsx", ".tsx", ".sh", ".bash", ".c", ".cpp",
    ".h", ".hpp", ".rs", ".go", ".java", ".sql", ".xml", ".toml", ".ini"
}


def is_supported_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS


def is_py_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".py"


def is_notebook_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".ipynb"


def detect_fence_language(path: Path) -> str:
    if is_py_file(path):
        return "python"
    if is_notebook_file(path):
        return "text"
    return ""


def normalize_cell_label(label: str) -> str:
    return str(label).strip().lower()


def parse_cell_selection(raw: str) -> Optional[List[str]]:
    raw = raw.strip().lower()
    if raw == "all":
        return None

    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        raise ValueError("Empty cell selection.")

    out: List[str] = []
    seen: Set[str] = set()

    for part in parts:
        if not re.fullmatch(r"\d+[a-z]?", part):
            raise ValueError(f"Invalid cell label: {part}")
        if part not in seen:
            out.append(part)
            seen.add(part)

    return out


# --------------------------------------------------
# Notebook parsing (.ipynb)
# --------------------------------------------------
def load_notebook_json(path: Path) -> dict:
    try:
        return json.loads(read_text_best_effort(path))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid notebook JSON: {path}") from exc


def notebook_cells(path: Path) -> List[dict]:
    data = load_notebook_json(path)
    cells = data.get("cells", [])
    if not isinstance(cells, list):
        raise ValueError("Notebook 'cells' field is not a list.")
    return cells


def summarize_ipynb_cells(path: Path, preview_len: int = 90) -> List[str]:
    cells = notebook_cells(path)
    lines: List[str] = []

    for i, cell in enumerate(cells, start=1):
        cell_type = str(cell.get("cell_type", "unknown")).strip().lower()
        source = cell.get("source", [])
        if isinstance(source, list):
            text = "".join(str(x) for x in source)
        else:
            text = str(source)

        preview = " ".join(text.strip().split())
        if len(preview) > preview_len:
            preview = preview[: preview_len - 3] + "..."
        if not preview:
            preview = "(empty)"

        lines.append(f"{str(i):>4} | {cell_type:<8} | {preview}")

    return lines


def _render_ipynb_outputs(outputs: list) -> str:
    parts: List[str] = []
    for out in outputs:
        out_type = str(out.get("output_type", "")).strip()
        if out_type == "stream":
            text = out.get("text", "")
            if isinstance(text, list):
                text = "".join(str(x) for x in text)
            if str(text).strip():
                parts.append(str(text).rstrip("\n"))
        elif out_type in ("execute_result", "display_data"):
            data = out.get("data", {})
            text = data.get("text/plain", "")
            if isinstance(text, list):
                text = "".join(str(x) for x in text)
            if str(text).strip():
                parts.append(str(text).rstrip("\n"))
        elif out_type == "error":
            ename = out.get("ename", "Error")
            evalue = out.get("evalue", "")
            traceback = out.get("traceback", [])
            tb_text = "\n".join(str(t) for t in traceback) if traceback else ""
            parts.append(f"{ename}: {evalue}" + (("\n" + tb_text) if tb_text else ""))
    return "\n".join(parts)


def append_plain_text(lines: List[str], text: str) -> None:
    stripped = text.rstrip("\n")
    if stripped:
        lines.append(stripped)


def render_ipynb(
    path: Path,
    selected_cells: Optional[List[str]],
    display_name: Optional[str] = None,
    cell_format: str = CELL_FORMAT_DIVIDER,
) -> str:
    cells = notebook_cells(path)
    total_cells = len(cells)
    valid_labels = [str(i) for i in range(1, total_cells + 1)]

    if selected_cells is None:
        wanted = valid_labels
    else:
        invalid = [idx for idx in selected_cells if normalize_cell_label(idx) not in valid_labels]
        if invalid:
            raise ValueError(
                f"Notebook has cell label(s): {', '.join(valid_labels)}. Invalid cell(s): {invalid}"
            )
        wanted = selected_cells

    lines: List[str] = []
    if display_name:
        lines.append(f"# ==========================================\n# File: {display_name}\n# ==========================================\n")
    if cell_format != CELL_FORMAT_LABELED:
        lines.append("```")

    for idx_label in wanted:
        idx = int(idx_label)
        cell = cells[idx - 1]
        cell_type = str(cell.get("cell_type", "unknown")).strip().lower()
        source = cell.get("source", [])
        text = "".join(str(x) for x in source) if isinstance(source, list) else str(source)

        if cell_format == CELL_FORMAT_LABELED:
            lines.append(f"[Cell {idx_label} | {cell_type}]")
            if cell_type == "code":
                lines.append("```python")
                lines.append(text.rstrip("\n"))
                lines.append("```")
            else:
                lines.append(text.rstrip("\n"))
        else:
            append_plain_text(lines, text)

        outputs = cell.get("outputs", [])
        if outputs:
            out_text = _render_ipynb_outputs(outputs)
            if out_text.strip():
                if cell_format == CELL_FORMAT_LABELED:
                    lines.append("")
                    lines.append(f"[Cell {idx_label} output]")
                    lines.append("```")
                    lines.append(out_text.rstrip("\n"))
                    lines.append("```")
                else:
                    append_plain_text(lines, out_text)

        if cell_format == CELL_FORMAT_LABELED:
            lines.append("")

    if cell_format != CELL_FORMAT_LABELED:
        lines.append("```")
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------
# Notebook-like .py parsing
# --------------------------------------------------
BANNER_LINE_RE = re.compile(r"^\s*#\s*={5,}\s*$")
NOTEBOOK_TITLE_RE = re.compile(r"#\s*.*notebook\b.*", re.IGNORECASE)

PY_CELL_MARKER_RE = re.compile(
    r"""
    ^
    \s*
    (?:
        \#\s*%%(?:\s*\[[^\]]+\])?      # # %% or # %% [code]
        |
        \#\s{0,3}cell\s*-?\d+[a-z]?\b(?!\s*[\)\]\,])(?:\s*[:\-—]|\s+[A-Za-z0-9_]|\s*$)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

PY_CELL_LABEL_RE = re.compile(
    r"#\s*cell\s*(-?\d+[a-z]?)\b(?!\s*[\)\]\,])",
    re.IGNORECASE,
)


def extract_cell_label_from_marker(header_line: str) -> Optional[str]:
    """Extract explicit cell labels like '8', '11b', or '12a'."""
    match = PY_CELL_LABEL_RE.search(header_line)
    if match:
        return normalize_cell_label(match.group(1))
    return None


def is_py_cell_marker_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return bool(PY_CELL_MARKER_RE.match(stripped))


def is_py_banner_header_start(lines: List[str], i: int) -> Tuple[bool, int, Optional[str], str]:
    if not BANNER_LINE_RE.match(lines[i].strip()):
        return False, 0, None, "code"

    for j in range(i + 1, min(len(lines), i + 6)):
        s = lines[j].strip()
        if BANNER_LINE_RE.match(s):
            inner = lines[i + 1:j]
            if not inner or not all(line.strip().startswith("#") for line in inner):
                return False, 0, None, "code"

            for line in inner:
                m_cell = PY_CELL_LABEL_RE.search(line)
                if m_cell:
                    return True, j + 1, normalize_cell_label(m_cell.group(1)), "code"

            for line in inner:
                if NOTEBOOK_TITLE_RE.search(line):
                    title = line.strip().lstrip("#").strip()[:40]
                    return True, j + 1, title, "markdown"
                if "[markdown]" in line.lower() or "[md]" in line.lower():
                    title = line.strip().lstrip("#").strip()[:40]
                    return True, j + 1, title, "markdown"

            return False, 0, None, "code"
        elif not s.startswith("#") and s:
            break

    return False, 0, None, "code"


def parse_py_cells(path: Path) -> List[dict]:
    """
    Split a .py file into notebook-like cells if cell marker lines exist.
    """
    text = read_text_best_effort(path)
    lines = text.splitlines(keepends=True)
    if not lines:
        return []

    boundaries: List[Tuple[int, int, Optional[str], str]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("# %%"):
            cell_type = "markdown" if "[markdown]" in stripped.lower() or "[md]" in stripped.lower() else "code"
            ahead = i + 1
            while ahead < len(lines) and not lines[ahead].strip():
                ahead += 1
            if ahead < len(lines):
                is_bh, end_bh, lbl, ctype = is_py_banner_header_start(lines, ahead)
                if is_bh:
                    boundaries.append((i, end_bh, lbl, cell_type if cell_type == "markdown" else ctype))
                    i = end_bh
                    continue
            boundaries.append((i, i + 1, None, cell_type))
            i += 1
            continue

        is_bh, end_bh, lbl, ctype = is_py_banner_header_start(lines, i)
        if is_bh:
            boundaries.append((i, end_bh, lbl, ctype))
            i = end_bh
            continue

        if is_py_cell_marker_line(line):
            lbl = extract_cell_label_from_marker(line)
            if i + 1 < len(lines) and BANNER_LINE_RE.match(lines[i + 1].strip()):
                boundaries.append((i, i + 2, lbl, "code"))
                i += 2
            else:
                boundaries.append((i, i + 1, lbl, "code"))
                i += 1
            continue

        i += 1

    if not boundaries:
        return [{
            "cell_type": "code",
            "source": text,
            "synthetic_single_cell": True,
            "from_markers": False,
            "cell_label": None,
        }]

    cells: List[dict] = []
    first_b_start = boundaries[0][0]
    if first_b_start > 0:
        preamble_lines = lines[:first_b_start]
        clean_preamble = [l for l in preamble_lines if not l.strip().startswith("```")]
        preamble_text = "".join(clean_preamble)
        if preamble_text.strip():
            cells.append({
                "cell_type": "code",
                "source": preamble_text if preamble_text.endswith("\n") else preamble_text + "\n",
                "synthetic_single_cell": False,
                "from_markers": True,
                "cell_label": "0",
            })

    for idx, (b_start, b_end, expl_lbl, c_type) in enumerate(boundaries):
        next_b_start = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else len(lines)

        cluster_lines = lines[b_start:b_end]
        raw_body_lines = lines[b_end:next_b_start]

        code_lines = []
        interstitial_md_lines = []
        in_interstitial = False

        k = 0
        while k < len(raw_body_lines):
            bline = raw_body_lines[k]
            bstripped = bline.strip()

            if bstripped == "```":
                rem = raw_body_lines[k + 1:]
                non_fence_text = [l for l in rem if not l.strip().startswith("```")]
                if any(l.strip() for l in non_fence_text):
                    in_interstitial = True
                    k += 1
                    continue
                else:
                    k += 1
                    continue

            if in_interstitial:
                if bstripped.startswith("```"):
                    in_interstitial = False
                else:
                    interstitial_md_lines.append(bline)
            else:
                if not bstripped.startswith("```"):
                    code_lines.append(bline)
            k += 1

        visible_code = "".join(cluster_lines + code_lines)
        clean_lines = [l for l in visible_code.splitlines(keepends=True) if not l.strip().startswith("```")]
        clean_source = "".join(clean_lines)
        if clean_source.strip():
            if not clean_source.endswith("\n"):
                clean_source += "\n"
            source_text = clean_source
            output_text = ""
            if c_type == "code":
                source_text, output_text = split_code_and_trailing_output(clean_source)
            cells.append({
                "cell_type": c_type,
                "source": source_text,
                "output_text": output_text,
                "synthetic_single_cell": False,
                "from_markers": True,
                "cell_label": expl_lbl or str(idx + 1),
            })

        clean_md = [l for l in interstitial_md_lines if not l.strip().startswith("```")]
        md_source = "".join(clean_md).strip()
        if md_source:
            cells.append({
                "cell_type": "markdown",
                "source": md_source + "\n\n",
                "output_text": "",
                "synthetic_single_cell": False,
                "from_markers": True,
                "cell_label": f"Note {len(cells)}",
            })

    return cells


def infer_py_cell_type_from_header(header_line: str) -> str:
    """
    Infer code/markdown from header if possible.
    Default: code
    """
    s = header_line.strip().lower()

    if "# %%" in s:
        if "[markdown]" in s or "[md]" in s:
            return "markdown"
        return "code"

    return "code"


def can_parse_python_block(text: str) -> bool:
    try:
        ast.parse(text)
        return True
    except SyntaxError:
        return False


def looks_like_notebook_output(text: str) -> bool:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False

    obvious_output = 0
    for line in lines:
        stripped = line.strip()
        if is_py_cell_marker_line(stripped) or stripped.startswith("!"):
            return False
        if stripped.startswith(("Traceback ", "Out[", "In [", "WARNING:", "WARN:", "Error:", "ERROR:")):
            obvious_output += 1
            continue
        if re.fullmatch(r"[=\-_*#]{5,}", stripped):
            obvious_output += 1
            continue
        if any(ch in stripped for ch in ("█", "▏", "▎", "▍", "▌", "▋", "▊", "▉")):
            obvious_output += 1
            continue
        if stripped.endswith("%") and any(ch.isdigit() for ch in stripped):
            obvious_output += 1
            continue

    return obvious_output > 0


def split_code_and_trailing_output(text: str) -> Tuple[str, str]:
    if not text.strip():
        return text, ""

    if can_parse_python_block(text):
        return text, ""

    lines = text.splitlines(keepends=True)
    for end in range(len(lines) - 1, 0, -1):
        candidate = "".join(lines[:end])
        remainder = "".join(lines[end:])
        if not remainder.strip():
            continue
        if not can_parse_python_block(candidate):
            continue
        if not looks_like_notebook_output(remainder):
            continue
        return candidate.rstrip("\n") + "\n", remainder.rstrip("\n") + "\n"

    return text, ""


def py_file_has_multiple_cells(path: Path) -> bool:
    cells = parse_py_cells(path)
    return len(cells) > 1 or bool(cells and cells[0].get("from_markers"))


def summarize_py_cells(path: Path, preview_len: int = 90) -> List[str]:
    cells = parse_py_cells(path)
    lines: List[str] = []

    for seq_idx, cell in enumerate(cells, start=1):
        cell_type = str(cell.get("cell_type", "code")).strip().lower()
        text = str(cell.get("source", ""))

        preview = " ".join(text.strip().split())
        if len(preview) > preview_len:
            preview = preview[: preview_len - 3] + "..."
        if not preview:
            preview = "(empty)"

        label = get_cell_display_label(cell, seq_idx)
        lines.append(f"{label:>4} | {cell_type:<8} | {preview}")

    return lines


def get_cell_display_label(cell: dict, sequential_counter: int) -> str:
    """Get the display label for a cell (explicit label or sequential counter)."""
    label = cell.get("cell_label")
    if label is not None:
        return str(label)
    return str(sequential_counter)


def get_render_labels_for_path(path: Path) -> List[str]:
    if is_notebook_file(path):
        return [str(i) for i in range(1, len(notebook_cells(path)) + 1)]
    if is_py_file(path):
        cells = parse_py_cells(path)
        return [get_cell_display_label(cell, i) for i, cell in enumerate(cells, start=1)]
    raise ValueError(f"Unsupported file type: {path}")


def render_py_with_cells(
    path: Path,
    selected_cells: Optional[List[str]],
    display_name: Optional[str] = None,
    cell_format: str = CELL_FORMAT_DIVIDER,
) -> str:
    cells = parse_py_cells(path)
    render_labels = [get_cell_display_label(cell, i) for i, cell in enumerate(cells, start=1)]
    label_map = {normalize_cell_label(lbl): idx for idx, lbl in enumerate(render_labels, start=1)}
    wanted_norm = None if selected_cells is None else {normalize_cell_label(x) for x in selected_cells}
    total_cells = len(render_labels)

    if selected_cells is None:
        wanted = render_labels
    else:
        invalid = [idx for idx in selected_cells if normalize_cell_label(idx) not in label_map]
        if invalid:
            raise ValueError(
                f"File has cell label(s): {', '.join(render_labels)}. Invalid cell(s): {invalid}"
            )
        wanted = selected_cells

    header = f"# ==========================================\n# File: {display_name}\n# ==========================================\n\n"
    lines = [header]
    if cell_format != CELL_FORMAT_LABELED:
        lines.append("```")

    rendered_count = 0
    for seq, cell in enumerate(cells, start=1):
        cell_label = get_cell_display_label(cell, seq)
        if wanted_norm is not None and normalize_cell_label(cell_label) not in wanted_norm:
            continue

        cell_type = str(cell.get("cell_type", "code")).strip().lower()
        text = str(cell.get("source", ""))
        output_text = str(cell.get("output_text", ""))

        rendered_count += 1
        if cell_format == CELL_FORMAT_LABELED:
            lines.append(f"[Cell {cell_label} | {cell_type}]")
            if cell_type == "markdown":
                lines.append(text.rstrip("\n"))
            else:
                lines.append("```python")
                lines.append(text.rstrip("\n"))
                lines.append("```")
        else:
            append_plain_text(lines, text)

        if output_text.strip():
            if cell_format == CELL_FORMAT_LABELED:
                lines.append("")
                lines.append(f"[Cell {cell_label} output]")
                lines.append("```")
                lines.append(output_text.rstrip("\n"))
                lines.append("```")
            else:
                append_plain_text(lines, output_text)

        if cell_format == CELL_FORMAT_LABELED:
            lines.append("")

    if cell_format != CELL_FORMAT_LABELED:
        lines.append("```")
    return "".join(lines).rstrip() + "\n"


def file_supports_cells(path: Path) -> bool:
    if is_notebook_file(path):
        return True
    if is_py_file(path):
        return True
    return False


def summarize_cells(path: Path, preview_len: int = 90) -> List[str]:
    if is_notebook_file(path):
        return summarize_ipynb_cells(path, preview_len=preview_len)
    if is_py_file(path):
        return summarize_py_cells(path, preview_len=preview_len)
    raise ValueError(f"Unsupported file type: {path}")


def count_cells(path: Path) -> int:
    return len(get_render_labels_for_path(path))


def render_file_content(
    path: Path,
    cell_selection_map: Dict[str, Optional[List[str]]],
    display_name: str,
    cell_format: str = CELL_FORMAT_DIVIDER,
) -> str:
    if is_notebook_file(path):
        return render_ipynb(path, cell_selection_map.get(display_name), display_name=display_name, cell_format=cell_format)
    if is_py_file(path):
        return render_py_with_cells(path, cell_selection_map.get(display_name), display_name=display_name, cell_format=cell_format)
    raise ValueError(f"Unsupported file type: {path}")


# --------------------------------------------------
# Discovery
# --------------------------------------------------
@dataclass
class FolderView:
    root: Path
    cwd: Path
    this_script: Path
    found: Dict[str, Path]
    visited_dirs: Set[str]

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        self.cwd = self.cwd.resolve()
        self.this_script = self.this_script.resolve()
        self.found = {}
        self.visited_dirs = set()

    def _assert_within_root(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.root)
            return True
        except Exception:
            return False

    def pwd(self) -> str:
        return safe_relpath(self.cwd, self.root)

    def list_current(self) -> Tuple[List[str], List[str]]:
        if not self.cwd.exists():
            return [], []

        self.visited_dirs.add(self.pwd())

        files: List[str] = []
        subdirs: List[str] = []

        for item in sorted(self.cwd.iterdir(), key=lambda x: x.name.lower()):
            if item.is_dir():
                subdirs.append(item.name)
            elif is_supported_file(item):
                if item.resolve() == self.this_script:
                    continue
                display = safe_relpath(item, self.root)
                files.append(display)
                self.found[display] = item

        return files, subdirs

    def cd(self, subfolder: str) -> bool:
        subfolder = normalize_user_input(subfolder)
        if not subfolder:
            return False

        target = (self.cwd / subfolder).resolve()
        if not target.exists() or not target.is_dir():
            return False
        if not self._assert_within_root(target):
            return False

        self.cwd = target
        return True

    def back(self) -> bool:
        if self.cwd == self.root:
            return False

        parent = self.cwd.parent.resolve()
        if not self._assert_within_root(parent):
            return False

        self.cwd = parent
        return True


# --------------------------------------------------
# Writers
# --------------------------------------------------
class MaxCharsPartWriter:
    def __init__(self, out_prefix: str, max_chars: int):
        self.out_prefix = out_prefix
        self.max_chars = max(1, max_chars)
        self.part_index = 0
        self.current_len = 0
        self.file = None
        self.written_files: List[str] = []
        self._start_new_part()

    def _start_new_part(self) -> None:
        if self.file:
            self.file.close()

        self.part_index += 1
        out_name = f"{self.out_prefix}{self.part_index}{OUT_SUFFIX}"
        self.file = open(out_name, "w", encoding="utf-8", newline="\n")
        self.written_files.append(out_name)

        self.current_len = 0

    def can_fit(self, text: str) -> bool:
        return self.current_len + len(text) <= self.max_chars

    def write(self, text: str) -> None:
        self.file.write(text)
        self.current_len += len(text)

    def rollover(self) -> None:
        self._start_new_part()

    def close(self) -> None:
        if self.file:
            self.file.close()
            self.file = None


class FixedPartsWriter:
    def __init__(self, out_prefix: str, num_parts: int, target_chars: int):
        self.out_prefix = out_prefix
        self.num_parts = max(1, num_parts)
        self.target_chars = max(1, target_chars)

        self.part_index = 0
        self.current_len = 0
        self.file = None
        self.written_files: List[str] = []

        self.current_header: Optional[str] = None
        self.current_fence_lang: str = ""
        self.in_code_block = False

        self._start_new_part(force_first=True)

    def _start_new_part(self, force_first: bool = False) -> None:
        if self.part_index >= self.num_parts and not force_first:
            return

        if self.file and self.in_code_block:
            self.file.write("\n```\n\n")
            self.in_code_block = False

        if self.file:
            self.file.close()

        self.part_index += 1
        out_name = f"{self.out_prefix}{self.part_index}{OUT_SUFFIX}"
        self.file = open(out_name, "w", encoding="utf-8", newline="\n")
        self.written_files.append(out_name)

        self.current_len = 0

        if self.current_header is not None:
            reopen = f"{self.current_header}\n```{self.current_fence_lang}\n"
            self.file.write(reopen)
            self.current_len += len(reopen)
            self.in_code_block = True

    def _should_roll(self, upcoming_len: int) -> bool:
        if self.part_index >= self.num_parts:
            return False
        return (self.current_len + upcoming_len) > self.target_chars

    def maybe_roll(self, upcoming_len: int) -> None:
        if self._should_roll(upcoming_len):
            self._start_new_part()

    def write(self, text: str) -> None:
        self.file.write(text)
        self.current_len += len(text)

    def start_file_block(self, display_name: str, fence_lang: str) -> None:
        header = f"{display_name}\n```{fence_lang}\n"
        self.current_header = display_name
        self.current_fence_lang = fence_lang
        self.maybe_roll(len(header))
        self.write(header)
        self.in_code_block = True

    def close_code_block_if_open(self) -> None:
        if not self.in_code_block:
            return

        tail = "\n```\n\n"
        if self._should_roll(len(tail)):
            self._start_new_part()
        self.write(tail)
        self.in_code_block = False

    def ensure_space_for_chunk(self, chunk_len: int) -> None:
        if not self._should_roll(chunk_len):
            return

        if self.in_code_block:
            self.file.write("\n```\n\n")
            self.in_code_block = False

        self._start_new_part()

        if self.current_header is not None and not self.in_code_block:
            reopen = f"{self.current_header}\n```{self.current_fence_lang}\n"
            self.write(reopen)
            self.in_code_block = True

    def close(self) -> None:
        if self.file:
            if self.in_code_block:
                self.file.write("\n```\n\n")
                self.in_code_block = False
            self.file.close()
            self.file = None


def estimate_total_output_chars(
    display_to_rendered: Dict[str, str],
    selected_display: List[str],
    out_parts: int,
) -> int:
    total = 0
    for display in selected_display:
        tail = "\n"
        content = display_to_rendered[display]
        total += len(content) + len(tail)

    return total


def write_rendered_content_lines(
    writer,
    display_name: str,
    content: str,
    max_chars: int,
    fixed_parts: bool = False,
) -> None:
    _ = display_name
    open_fence: Optional[str] = None
    lines = content.splitlines(keepends=True)

    for line in lines:
        stripped = line.strip()
        is_fence = stripped.startswith("```")

        closing_len = 4 if open_fence is not None else 0
        if writer.current_len + len(line) + closing_len > max_chars:
            if open_fence is not None:
                writer.write("```\n")
            writer.rollover() if not fixed_parts else writer._start_new_part()
            if open_fence is not None:
                writer.write(open_fence + "\n")

        writer.write(line)

        if is_fence:
            if open_fence is None:
                open_fence = stripped
            else:
                open_fence = None

    if open_fence is not None:
        if writer.current_len + 4 > max_chars:
            writer.rollover() if not fixed_parts else writer._start_new_part()
        writer.write("```\n")

    if writer.current_len + 1 > max_chars:
        writer.rollover() if not fixed_parts else writer._start_new_part()
    writer.write("\n")


# --------------------------------------------------
# Combine logic
# --------------------------------------------------
def combine_files(
    root: Path,
    display_to_path: Dict[str, Path],
    selected_display: List[str],
    excluded_display: Set[str],
    cell_selection_map: Dict[str, Optional[List[str]]],
    mode: str,
    max_chars: int,
    num_parts: int,
    out_prefix: str,
    cell_format: str,
    custom_pattern: str = "",
) -> None:
    final_display = [d for d in selected_display if d not in excluded_display]
    final_paths = [display_to_path[d] for d in final_display if d in display_to_path]

    if not final_paths:
        print("No files to write (after exclusion / selection).")
        return

    rendered_map: Dict[str, str] = {}
    for display in final_display:
        path = display_to_path[display]
        rendered_map[display] = render_file_content(
            path,
            cell_selection_map,
            display,
            cell_format=cell_format,
        )

    print("\nRendered source character counts:")
    for display in final_display:
        print(f" - {display}: {len(rendered_map[display])} chars")
    print(f" - TOTAL: {sum(len(rendered_map[d]) for d in final_display)} chars")

    total_chars = estimate_total_output_chars(
        rendered_map,
        final_display,
        0,
    )

    if mode == "maxchars":
        base_parts = max(1, (total_chars + max_chars - 1) // max_chars)
    else:
        base_parts = max(1, num_parts)

    if custom_pattern.strip():
        # Parse multiplication coefficients
        cleaned = custom_pattern.replace(":", ",").replace("x", "").strip()
        tokens = [t.strip() for t in cleaned.split(",") if t.strip()]
        coeffs = []
        for t in tokens:
            try:
                num = float(t)
                if num > 0:
                    coeffs.append(num)
            except ValueError:
                continue

        if mode == "fixedparts":
            if not coeffs:
                coeffs = [1.0] * base_parts
            elif len(coeffs) < base_parts:
                coeffs = coeffs + [1.0] * (base_parts - len(coeffs))
            elif len(coeffs) > base_parts:
                coeffs = coeffs[:base_parts]
            sum_c = sum(coeffs)
            target_sizes = [max(1, int(round((c / sum_c) * total_chars))) for c in coeffs]
        else:
            avg_target = (total_chars + base_parts - 1) // base_parts
            if not coeffs:
                target_sizes = [min(max_chars, avg_target)] * base_parts
            else:
                target_sizes = []
                for i in range(max(base_parts, len(coeffs))):
                    c = coeffs[i] if i < len(coeffs) else 1.0
                    scaled = int(round(avg_target * c))
                    target_sizes.append(max(1, min(max_chars, scaled)))

        calculated_parts = len(target_sizes)
        avg_target = sum(target_sizes) // max(1, calculated_parts)
        print(
            f"Multipliers distribution split: {total_chars} chars across {calculated_parts} part(s)"
        )
        writer = FixedPartsWriter(
            out_prefix=out_prefix,
            num_parts=calculated_parts,
            target_chars=avg_target,
        )

        try:
            for display in final_display:
                content = rendered_map[display]
                write_rendered_content_lines(
                    writer=writer,
                    display_name=display,
                    content=content,
                    max_chars=writer.target_chars,
                    fixed_parts=True,
                )

            writer.close()

            print("\nDone! Wrote the following files:")
            for name in writer.written_files:
                print(f" - {name}: {len(read_text_best_effort(Path(name)))} chars")

        finally:
            try:
                writer.close()
            except Exception:
                pass

    elif mode == "maxchars":
        calculated_parts = base_parts
        target = (total_chars + calculated_parts - 1) // calculated_parts

        print(
            f"Balanced split: {total_chars} chars / {calculated_parts} part(s) "
            f"= about {target} chars per part"
        )

        writer = FixedPartsWriter(
            out_prefix=out_prefix,
            num_parts=calculated_parts,
            target_chars=target,
        )

        try:
            for display in final_display:
                content = rendered_map[display]
                write_rendered_content_lines(
                    writer=writer,
                    display_name=display,
                    content=content,
                    max_chars=writer.target_chars,
                    fixed_parts=True,
                )

            writer.close()

            print("\nDone! Wrote the following files:")
            for name in writer.written_files:
                print(f" - {name}: {len(read_text_best_effort(Path(name)))} chars")

        finally:
            try:
                writer.close()
            except Exception:
                pass

    else:
        target = (total_chars + num_parts - 1) // num_parts
        writer = FixedPartsWriter(
            out_prefix=out_prefix,
            num_parts=num_parts,
            target_chars=target,
        )

        try:
            for display in final_display:
                content = rendered_map[display]
                write_rendered_content_lines(
                    writer=writer,
                    display_name=display,
                    content=content,
                    max_chars=writer.target_chars,
                    fixed_parts=True,
                )

            writer.close()

            print("\nDone! Wrote the following files:")
            for name in writer.written_files:
                print(f" - {name}: {len(read_text_best_effort(Path(name)))} chars")

        finally:
            try:
                writer.close()
            except Exception:
                pass


# --------------------------------------------------
# Interactive UI
# --------------------------------------------------
HELP_TEXT = r"""
Commands (navigation):
  ls                          -> list supported files in current folder + show subfolders
  pwd                         -> show current folder
  cd <subfolder/path>         -> enter a subfolder
  back                        -> go to parent folder

Commands (selection):
  add <file>                  -> add a .py or .ipynb file
  remove <file>               -> remove from selection
  addall                      -> add all supported files in current folder
  clear                       -> clear selection
  selected                    -> show selected files

Commands (exclude/include):
  exclude <file>              -> exclude from output
  include <file>              -> include back
  excluded                    -> show excluded files

Notebook / cell commands:
  nbinfo <file>               -> show cells for .ipynb or notebook-like .py
  cells <file> all            -> export all cells
  cells <file> 1,5,6          -> export only selected cells
  cells <file> 2,2b,12a       -> export explicit Python cell labels
  clearcells <file>           -> reset to all cells
  cellmap                     -> show current cell selections

Commands (discovery overview):
  listall                     -> list all found supported files

Commands (output):
  write                       -> generate txt output
  help                        -> show this help
  quit                        -> exit

Notes:
- File arguments can be exact displayed path or basename if unique.
- Notebook cells are 1-based.
- Python files preserve explicit labels like `2b` and `12a`.
- For .py files, cell markers such as '# %%' and 'Cell 1:' are recognized.
- During write, plain fenced output is the default; choose labeled cells for the old [Cell ...] format.
"""


def resolve_display_arg(arg: str, found_map: Dict[str, Path]) -> Optional[str]:
    arg = normalize_user_input(arg)
    if not arg:
        return None

    lower_to_display = {k.lower(): k for k in found_map.keys()}
    if arg.lower() in lower_to_display:
        return lower_to_display[arg.lower()]

    base = Path(arg).name.lower()
    matches = [d for d in found_map.keys() if Path(d).name.lower() == base]

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        print("Multiple matches for that basename. Use the full path shown in ls/listall:")
        for match in sorted(matches, key=lambda x: x.lower()):
            print(f" - {match}")
        return None

    return None


def ask_int(prompt: str, default: int, min_value: int = 1) -> int:
    while True:
        try:
            raw = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("")
            return default

        if raw == "":
            return default

        try:
            value = int(raw)
        except ValueError:
            print("Please enter a valid integer.")
            continue

        if value < min_value:
            print(f"Please enter >= {min_value}.")
            continue

        return value


def ask_split_mode() -> Tuple[str, int, int, str]:
    print("\nOutput split mode:")
    print(f"  1) Balanced split using max chars (default {DEFAULT_MAX_CHARS})")
    print(f"  2) Split into EXACTLY N parts (default {DEFAULT_NUM_PARTS})")

    while True:
        try:
            choice = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("")
            choice = "1"

        if choice in ("1", ""):
            max_chars = ask_int(
                f"Max chars per part? [default {DEFAULT_MAX_CHARS}]: ",
                DEFAULT_MAX_CHARS,
                50,
            )
            try:
                pattern = input("Optional part multipliers (e.g. 1.5, 1.0 or 2, 1) [Enter for default]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("")
                pattern = ""
            return "maxchars", max_chars, DEFAULT_NUM_PARTS, pattern

        if choice == "2":
            num_parts = ask_int(
                f"How many parts? [default {DEFAULT_NUM_PARTS}]: ",
                DEFAULT_NUM_PARTS,
                1,
            )
            try:
                pattern = input("Optional part multipliers (e.g. 1.5, 1.0 or 2, 1) [Enter for default]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("")
                pattern = ""
            return "fixedparts", DEFAULT_MAX_CHARS, num_parts, pattern

        print("Please type 1 or 2.")


def ask_out_prefix(mode: str) -> str:
    default_prefix = (
        "combined_text_by_chars_part_"
        if mode == "maxchars"
        else "combined_text_fixed_parts_part_"
    )

    try:
        raw = input(f"Output prefix? [default {default_prefix}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("")
        return default_prefix

    if raw == "":
        return default_prefix

    return raw.replace(" ", "_")


def ask_cell_format() -> str:
    print("\nCell output style:")
    print("  1) Plain fenced (default; no headers, labels, or separators)")
    print("  2) Labeled cells (old format)")

    while True:
        try:
            choice = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("")
            return CELL_FORMAT_DIVIDER

        if choice in ("", "1"):
            return CELL_FORMAT_DIVIDER

        if choice == "2":
            return CELL_FORMAT_LABELED

        print("Please type 1 or 2.")


def print_supported_files(
    files: List[str],
    subdirs: List[str],
    selected_set: Set[str],
    excluded: Set[str],
    found_map: Dict[str, Path],
) -> None:
    if subdirs:
        print("Subfolders (not scanned):")
        for folder in subdirs:
            print(f"  [D] {folder}")
    else:
        print("Subfolders: (none)")

    if files:
        print("Supported files (current folder only):")
        for display in files:
            path = found_map[display]
            kind = "NB" if is_notebook_file(path) else "PY"
            sel = " [selected]" if display in selected_set else ""
            exc = " [excluded]" if display in excluded else ""
            print(f"  [{kind}] {display}{sel}{exc}")
    else:
        print("Supported files: (none)")


def main() -> None:
    root = Path(".").resolve()
    this_script = Path(__file__).resolve()

    view = FolderView(
        root=root,
        cwd=root,
        this_script=this_script,
        found={},
        visited_dirs=set(),
    )

    selected: List[str] = []
    selected_set: Set[str] = set()
    excluded: Set[str] = set()
    cell_selection_map: Dict[str, Optional[List[str]]] = {}

    print("pytotext2.py")
    print(f"Start folder: {root}")
    print("Type 'help' for commands.\n")

    files, subdirs = view.list_current()
    if files:
        print("Initial scan (current folder only):")
        for display in files:
            print(f" - {display}")
    else:
        print("No supported files found in the current folder yet (try cd/ls).")

    if subdirs:
        print("\nSubfolders (not scanned):")
        for folder in subdirs:
            print(f" - {folder}")
    print("")

    while True:
        try:
            raw = input("> ")
        except (EOFError, KeyboardInterrupt):
            print("\nquit")
            break

        line = normalize_user_input(raw)
        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()
        arg = " ".join(parts[1:]) if len(parts) > 1 else ""

        if cmd in {"help", "?"}:
            print(HELP_TEXT)
            continue

        if cmd in {"quit", "exit", "q"}:
            break

        if cmd == "pwd":
            print(view.pwd())
            continue

        if cmd == "ls":
            files, subdirs = view.list_current()
            print(f"\nFolder: {view.pwd()}")
            print_supported_files(files, subdirs, selected_set, excluded, view.found)
            print("")
            continue

        if cmd == "cd":
            if not arg:
                print("Usage: cd <subfolder>")
                continue

            if not view.cd(arg):
                print("Cannot cd there (must exist, be a folder, and stay inside the start folder).")
                continue

            files, subdirs = view.list_current()
            print(f"Now in: {view.pwd()}")
            if subdirs:
                print("Subfolders (not scanned): " + ", ".join(subdirs))
            print(f"Supported files here: {len(files)}")
            continue

        if cmd == "back":
            if not view.back():
                print("Already at start folder.")
                continue
            view.list_current()
            print(f"Now in: {view.pwd()}")
            continue

        if cmd == "listall":
            if not view.found:
                print("No files found yet. Use ls or cd into folders first.")
                continue

            print("\nALL found supported files:")
            for display in sorted(view.found.keys(), key=lambda x: x.lower()):
                path = view.found[display]
                kind = "NB" if is_notebook_file(path) else "PY"
                sel = " [selected]" if display in selected_set else ""
                exc = " [excluded]" if display in excluded else ""
                print(f" - [{kind}] {display}{sel}{exc}")
            print("")
            continue

        if cmd == "selected":
            if not selected:
                print("Selected: (none)")
                continue

            print("\nSelected files:")
            for display in selected:
                path = view.found.get(display)
                kind = "NB" if path and is_notebook_file(path) else "PY"
                exc = " [excluded]" if display in excluded else ""
                cells_info = ""
                if path and file_supports_cells(path):
                    selection = cell_selection_map.get(display)
                    if selection is None:
                        cells_info = " [cells: all]"
                    else:
                        cells_info = f" [cells: {','.join(map(str, selection))}]"
                print(f" - [{kind}] {display}{exc}{cells_info}")
            print("")
            continue

        if cmd == "addall":
            files, _ = view.list_current()
            if not files:
                print("No supported files in current folder to add.")
                continue

            added = 0
            for display in files:
                if display not in selected_set:
                    selected.append(display)
                    selected_set.add(display)
                    if display not in cell_selection_map and file_supports_cells(view.found[display]):
                        cell_selection_map[display] = None
                    added += 1

            print(f"Added {added} files from current folder.")
            continue

        if cmd == "clear":
            selected.clear()
            selected_set.clear()
            cell_selection_map.clear()
            print("Selection cleared.")
            continue

        if cmd == "add":
            if not arg:
                print("Usage: add <file>")
                continue

            display = resolve_display_arg(arg, view.found)
            if display is None:
                print("Not found among discovered files. Use ls or listall.")
                continue

            if display in selected_set:
                print(f"Already selected: {display}")
                continue

            selected.append(display)
            selected_set.add(display)
            if file_supports_cells(view.found[display]) and display not in cell_selection_map:
                cell_selection_map[display] = None
            print(f"Added: {display}")
            continue

        if cmd == "remove":
            if not arg:
                print("Usage: remove <file>")
                continue

            display = resolve_display_arg(arg, view.found)
            if display is None or display not in selected_set:
                print("That file is not selected.")
                continue

            selected_set.remove(display)
            selected = [x for x in selected if x != display]
            cell_selection_map.pop(display, None)
            print(f"Removed: {display}")
            continue

        if cmd == "excluded":
            if not excluded:
                print("Excluded: (none)")
                continue

            print("\nExcluded files:")
            for display in sorted(excluded, key=lambda x: x.lower()):
                sel = " [selected]" if display in selected_set else ""
                print(f" - {display}{sel}")
            print("")
            continue

        if cmd == "exclude":
            if not arg:
                print("Usage: exclude <file>")
                continue

            display = resolve_display_arg(arg, view.found)
            if display is None:
                print("Not found among discovered files. Use ls/listall first.")
                continue

            excluded.add(display)
            print(f"Excluded: {display}")
            continue

        if cmd == "include":
            if not arg:
                print("Usage: include <file>")
                continue

            display = resolve_display_arg(arg, view.found)
            if display is None:
                print("Not found among discovered files. Use ls/listall first.")
                continue

            if display in excluded:
                excluded.remove(display)
                print(f"Included back: {display}")
            else:
                print("That file was not excluded.")
            continue

        if cmd == "nbinfo":
            if not arg:
                print("Usage: nbinfo <file>")
                continue

            display = resolve_display_arg(arg, view.found)
            if display is None:
                print("Not found among discovered files. Use ls/listall first.")
                continue

            path = view.found[display]
            if not file_supports_cells(path):
                print("That file does not support cell inspection.")
                continue

            try:
                lines = summarize_cells(path)
                print(f"\nCells for: {display}")
                if not lines:
                    print("  (no cells)")
                else:
                    print(" cell | type     | preview")
                    print("------+----------+--------------------------------------------------------------")
                    for line_out in lines:
                        print(line_out)
                print("")
            except Exception as exc:
                print(f"Cell inspection failed: {exc}")
            continue

        if cmd == "cells":
            if not arg:
                print("Usage: cells <file> all")
                print("   or: cells <file> 1,5,6")
                continue

            split_once = arg.split(maxsplit=1)
            if len(split_once) < 2:
                print("Usage: cells <file> all")
                print("   or: cells <file> 1,5,6")
                continue

            file_arg, cells_arg = split_once[0], split_once[1]
            display = resolve_display_arg(file_arg, view.found)
            if display is None:
                print("Not found among discovered files. Use ls/listall first.")
                continue

            path = view.found[display]
            if not file_supports_cells(path):
                print("That file does not support cell selection.")
                continue

            try:
                selection = parse_cell_selection(cells_arg)
                if selection is not None:
                    valid_labels = {normalize_cell_label(x) for x in get_render_labels_for_path(path)}
                    invalid = [idx for idx in selection if normalize_cell_label(idx) not in valid_labels]
                    if invalid:
                        print(f"File has cell label(s): {', '.join(get_render_labels_for_path(path))}")
                        print(f"Invalid cell(s): {invalid}")
                        continue

                cell_selection_map[display] = selection
                if selection is None:
                    print(f"Cells set to ALL for: {display}")
                else:
                    print(f"Cells set for {display}: {selection}")
            except Exception as exc:
                print(f"Could not set cells: {exc}")
            continue

        if cmd == "clearcells":
            if not arg:
                print("Usage: clearcells <file>")
                continue

            display = resolve_display_arg(arg, view.found)
            if display is None:
                print("Not found among discovered files. Use ls/listall first.")
                continue

            path = view.found[display]
            if not file_supports_cells(path):
                print("That file does not support cell selection.")
                continue

            cell_selection_map[display] = None
            print(f"Cell selection cleared (now ALL): {display}")
            continue

        if cmd == "cellmap":
            items = [d for d in selected if d in view.found and file_supports_cells(view.found[d])]
            if not items:
                print("No selected files with cell support.")
                continue

            print("\nCell selections:")
            for display in items:
                selection = cell_selection_map.get(display)
                if selection is None:
                    print(f" - {display}: all")
                else:
                    print(f" - {display}: {selection}")
            print("")
            continue

        if cmd == "write":
            if not selected:
                print("Nothing selected. Use add/addall first.")
                continue

            missing = [s for s in selected if s not in view.found]
            if missing:
                print("Some selected items are not in the discovered map.")
                for item in missing:
                    print(f" - {item}")
                continue

            mode, max_chars, num_parts, custom_pattern = ask_split_mode()
            out_prefix = ask_out_prefix(mode)
            cell_format = ask_cell_format()

            effective = [s for s in selected if s not in excluded]

            print("\nAbout to write:")
            print(f" - Selected: {len(selected)}")
            print(f" - Excluded: {len(excluded)}")
            print(f" - Effective: {len(effective)}")
            if mode == "maxchars":
                print(f" - Mode: max chars per part = {max_chars}")
            elif mode == "custom":
                print(f" - Mode: custom split pattern = {custom_pattern}")
            else:
                print(f" - Mode: fixed parts = {num_parts}")
            print(f" - Output prefix: {out_prefix}")
            print(
                " - Cell output style: "
                + ("plain fenced" if cell_format == CELL_FORMAT_DIVIDER else "labeled cells")
            )

            cell_files = [
                d for d in effective
                if d in view.found and file_supports_cells(view.found[d])
            ]
            if cell_files:
                print(" - Cell selections:")
                for display in cell_files:
                    selection = cell_selection_map.get(display)
                    if selection is None:
                        print(f"    - {display}: all")
                    else:
                        print(f"    - {display}: {selection}")
            print("")

            try:
                combine_files(
                    root=view.root,
                    display_to_path=view.found,
                    selected_display=selected,
                    excluded_display=excluded,
                    cell_selection_map=cell_selection_map,
                    mode=mode,
                    max_chars=max_chars,
                    num_parts=num_parts,
                    out_prefix=out_prefix,
                    cell_format=cell_format,
                    custom_pattern=custom_pattern,
                )
            except Exception as exc:
                print(f"Write failed: {exc}")
            continue

        print("Unknown command. Type 'help' to see commands.")


if __name__ == "__main__":
    main()
