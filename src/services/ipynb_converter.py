"""Convert between notebook cell format and IPYNB (Jupyter Notebook) format."""

from __future__ import annotations

import uuid


def cells_to_ipynb(cells: list[dict]) -> dict:
    """Convert internal cell list to IPYNB (nbformat v4)."""
    ipynb_cells = []
    for cell in cells:
        cell_type = cell.get("type", "code")
        source = cell.get("source", "") or ""
        source_lines = source.splitlines(keepends=True)
        if not source_lines:
            source_lines = [""]

        ipynb_cell: dict = {
            "cell_type": cell_type,
            "metadata": {},
            "source": source_lines,
        }

        if cell_type == "code":
            outputs = _outputs_to_ipynb(cell.get("outputs", []))
            ipynb_cell["outputs"] = outputs
            # Derived from the cell's own outputs rather than invented: a cell
            # that has not produced an execute_result stays null, which is
            # what nbformat expects for an unexecuted cell.
            counts = [
                o["execution_count"]
                for o in outputs
                if o.get("output_type") == "execute_result"
                and o.get("execution_count") is not None
            ]
            ipynb_cell["execution_count"] = counts[-1] if counts else None

        ipynb_cells.append(ipynb_cell)

    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.10.0"},
        },
        "cells": ipynb_cells,
    }


def ipynb_to_cells(ipynb: dict) -> list[dict]:
    """Convert IPYNB dict to internal cell list."""
    cells = []
    for ipynb_cell in ipynb.get("cells", []):
        cell_type = ipynb_cell.get("cell_type", "code")
        source_raw = ipynb_cell.get("source", [])
        source = _join_source(source_raw)

        cell: dict = {
            "id": str(uuid.uuid4()),
            "type": cell_type,
            "source": source,
            "outputs": [],
            "is_running": False,
        }

        if cell_type == "code":
            cell["outputs"] = _outputs_from_ipynb(ipynb_cell.get("outputs", []))

        cells.append(cell)

    return cells


def cells_to_py(cells: list[dict]) -> str:
    """Convert an internal cell list to a `# %%`-marked Python script.

    The exact inverse of :func:`py_to_cells`, so an exported script re-imports
    as the same cells. Code blocks emit a bare ``# %%``; markdown blocks emit
    ``# %% [markdown]`` followed by the cell body.

    Round-trip guarantee: ``py_to_cells(cells_to_py(cells)) == cells`` for
    cells whose source is non-empty and does not itself begin with a ``# %%``
    line. ``py_to_cells`` skips empty blocks, so an empty cell cannot survive
    the trip — a property of the percent format, not a bug to paper over.
    """
    blocks: list[str] = []
    for cell in cells:
        source = (cell.get("source", "") or "").rstrip("\n")
        if not source.strip():
            continue
        if cell.get("type") == "markdown":
            blocks.append(f"# %% [markdown]\n{source}")
        else:
            blocks.append(f"# %%\n{source}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _split_script_blocks(source: str) -> list[dict]:
    """Split a `# %%`-marked script into non-empty blocks, with ranges.

    Each block is ``{"type", "source", "start", "end"}``; the offsets index
    into *source*, so a caret position resolves to its block in a single pass.
    Empty blocks are omitted — they cannot survive a round trip anyway, and
    carrying them would make block 0 of a marker-prefixed file a phantom.
    """
    text = source or ""
    lines = text.splitlines(keepends=True)
    blocks: list[dict] = []
    block_type = "code"
    block_lines: list[str] = []
    block_start = 0
    cursor = 0

    def _flush(end: int) -> None:
        nonlocal block_lines
        body = "".join(block_lines).strip("\n")
        if body:
            blocks.append(
                {
                    "type": block_type,
                    "source": body,
                    "start": block_start,
                    "end": end,
                }
            )
        block_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# %%"):
            # Flush before the marker changes block_type.
            _flush(cursor)
            marker = stripped[len("# %%") :].strip()
            if marker.lower().startswith("[markdown]"):
                block_type = "markdown"
                # `# %% [markdown] Title` — keep the title as the cell body.
                title = marker[len("[markdown]") :].strip()
                block_lines = [title + "\n"] if title else []
            else:
                block_type = "code"
                block_lines = []
            block_start = cursor + len(line)
        else:
            block_lines.append(line)
        cursor += len(line)
    _flush(len(text))
    return blocks


def _script_blocks(source: str) -> list[dict]:
    """Non-empty script blocks (kept as a named seam for callers/tests)."""
    return _split_script_blocks(source)


def py_to_cells(source: str) -> list[dict]:
    """Convert a Python source file to internal cells.

    Files using Jupyter/VS Code `# %%` cell markers are split into one code
    cell per block; a `# %% [markdown]` marker starts a markdown cell. Files
    without markers become a single code cell.
    """
    cells = [
        {
            "id": str(uuid.uuid4()),
            "type": block["type"],
            "source": block["source"],
            "outputs": [],
            "is_running": False,
        }
        for block in _script_blocks(source)
    ]
    return cells or [
        {
            "id": str(uuid.uuid4()),
            "type": "code",
            "source": "",
            "outputs": [],
            "is_running": False,
        }
    ]


def block_at_offset(source: str, offset: int) -> str:
    """Return the source of the `# %%` block containing *offset*.

    Falls back to the first block when the caret sits in marker or blank
    space that belongs to no block, and to the whole text when the file has
    no markers at all.
    """
    blocks = _script_blocks(source)
    if not blocks:
        return source or ""
    for block in blocks:
        if block["start"] <= offset < block["end"]:
            return block["source"]
    return blocks[0]["source"]


def merge_script_cells(old_cells: list[dict], new_cells: list[dict]) -> list[dict]:
    """Fold re-split script cells back into the existing cell list.

    Editing a script re-derives the cell list, and every freshly parsed cell
    arrives with ``outputs: []`` — which would wipe the plots and tracebacks
    of cells the user never touched. Instead a new cell inherits the id and
    outputs of an old cell with the same type and source, so an edited cell
    loses only its own (now stale) output and everything else is untouched.

    Matching on type+source rather than index means inserting a block in the
    middle does not churn the ids of the blocks after it, so editors keep
    their state and focus.
    """
    remaining = list(old_cells or [])
    merged: list[dict] = []

    for new in new_cells or []:
        carry = None
        for index, old in enumerate(remaining):
            if (
                old.get("type") == new.get("type")
                and (old.get("source") or "") == (new.get("source") or "")
            ):
                carry = remaining.pop(index)
                break
        if carry is None:
            merged.append(dict(new))
            continue
        entry = dict(carry)
        entry["type"] = new.get("type", entry.get("type"))
        entry["source"] = new.get("source", entry.get("source"))
        merged.append(entry)

    return merged


def _join_source(source_raw) -> str:
    if isinstance(source_raw, list):
        return "".join(source_raw)
    return str(source_raw) if source_raw else ""


def _outputs_to_ipynb(outputs: list[dict]) -> list[dict]:
    """Internal output dicts -> nbformat v4 output dicts.

    Accepts both our stored shape (``type``) and already-nbformat-shaped
    dicts (``output_type``), so a notebook round-tripped through an import
    still exports cleanly.
    """
    result = []
    for out in outputs:
        t = out.get("type") or out.get("output_type") or ""
        if t == "stream":
            result.append(
                {
                    "output_type": "stream",
                    "name": out.get("name", "stdout"),
                    "text": _as_text_lines(out.get("text", "")),
                }
            )
        elif t == "error":
            result.append(
                {
                    "output_type": "error",
                    "ename": out.get("ename", ""),
                    "evalue": out.get("evalue", ""),
                    "traceback": out.get("traceback", []),
                }
            )
        elif t in ("execute_result", "display_data"):
            entry: dict = {
                "output_type": t,
                "data": out.get("data", {}),
                "metadata": out.get("metadata", {}),
            }
            if t == "execute_result":
                # Carried through from the kernel — never silently blanked.
                entry["execution_count"] = out.get("execution_count")
            else:
                entry["transient"] = out.get("transient", {})
            result.append(entry)
        else:
            result.append(out)
    return result


def _outputs_from_ipynb(outputs: list[dict]) -> list[dict]:
    """nbformat v4 output dicts -> our stored shape (``type``).

    ``display_data`` is kept: a chart in an imported notebook is a real
    output, and silently dropping it lost the plot on every re-export.
    """
    result = []
    for out in outputs:
        ot = out.get("output_type", "")
        if ot == "stream":
            text_raw = out.get("text", "")
            text = "".join(text_raw) if isinstance(text_raw, list) else str(text_raw)
            result.append({"type": "stream", "text": text, "name": out.get("name", "stdout")})
        elif ot == "error":
            result.append(
                {
                    "type": "error",
                    "ename": out.get("ename", ""),
                    "evalue": out.get("evalue", ""),
                    "traceback": out.get("traceback", []),
                }
            )
        elif ot in ("execute_result", "display_data"):
            entry = {
                "type": ot,
                "data": out.get("data", {}),
                "metadata": out.get("metadata", {}),
            }
            if ot == "execute_result":
                entry["execution_count"] = out.get("execution_count")
            else:
                entry["transient"] = out.get("transient", {})
            result.append(entry)
        else:
            result.append(out)
    return result


def _as_text_lines(text) -> list[str]:
    """nbformat stores stream/source text as a list of lines."""
    if isinstance(text, list):
        return text
    s = str(text) if text is not None else ""
    return [s] if s else [""]
