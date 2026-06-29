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
            ipynb_cell["outputs"] = _outputs_to_ipynb(cell.get("outputs", []))
            ipynb_cell["execution_count"] = None

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


def _join_source(source_raw) -> str:
    if isinstance(source_raw, list):
        return "".join(source_raw)
    return str(source_raw) if source_raw else ""


def _outputs_to_ipynb(outputs: list[dict]) -> list[dict]:
    result = []
    for out in outputs:
        t = out.get("type", "")
        if t == "stream":
            result.append(
                {
                    "output_type": "stream",
                    "name": "stdout",
                    "text": [out.get("text", "")],
                }
            )
        elif t == "error":
            result.append(
                {
                    "output_type": "error",
                    "ename": "",
                    "evalue": "",
                    "traceback": out.get("traceback", []),
                }
            )
        else:
            result.append(out)
    return result


def _outputs_from_ipynb(outputs: list[dict]) -> list[dict]:
    result = []
    for out in outputs:
        ot = out.get("output_type", "")
        if ot == "stream":
            text_raw = out.get("text", "")
            text = "".join(text_raw) if isinstance(text_raw, list) else str(text_raw)
            result.append({"type": "stream", "text": text})
        elif ot == "error":
            result.append({"type": "error", "traceback": out.get("traceback", [])})
        elif ot == "display_data":
            continue
        else:
            result.append(out)
    return result
