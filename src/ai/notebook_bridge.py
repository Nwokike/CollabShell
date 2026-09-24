"""The Assistant's handle on the notebook the user is looking at.

`NotebookView` owns the cells, so it builds one of these per mount and
hands it to the session. Every method is a closure over that view's own
state, which is the whole point: a tool call writes a cell through the
same list the screen is rendering, so the user watches the edit land
live in the notebook behind the chat sheet instead of being told about
it later.

A bridge is valid only while its view is mounted. Leaving the session
detaches it, and the tools disappear from the catalog with it rather
than pointing at a dead notebook.
"""

from __future__ import annotations

from collections.abc import Callable


class NotebookBridge:
    """Read/write access to one mounted notebook.

    Args:
        session_name: which Colab session's notebook this is.
        snapshot: () -> list of cell dicts, in display order.
        read: (ref) -> str, the full source plus output of one cell.
        set_source: (ref, source) -> str, replace a cell's code.
        insert: (after_ref, type, source) -> str, add a cell.
        run: async (ref) -> str, run a cell to completion.
        alive: () -> bool, false once the view is gone.
    """

    def __init__(
        self,
        session_name: str,
        snapshot: Callable[[], list],
        read: Callable[[str], str],
        set_source: Callable[[str, str], str],
        insert: Callable[[str | None, str, str], str],
        run: Callable[[str], object],
        alive: Callable[[], bool] | None = None,
    ):
        self.session_name = session_name
        self._snapshot = snapshot
        self._read = read
        self._set_source = set_source
        self._insert = insert
        self._run = run
        self._alive = alive or (lambda: True)

    def is_alive(self) -> bool:
        return self._alive()

    def cells(self) -> list:
        return self._snapshot()

    def read(self, ref: str) -> str:
        return self._read(ref)

    def set_source(self, ref: str, source: str) -> str:
        return self._set_source(ref, source)

    def insert(self, after_ref: str | None, cell_type: str, source: str) -> str:
        return self._insert(after_ref, cell_type, source)

    async def run(self, ref: str) -> str:
        result = self._run(ref)
        if hasattr(result, "__await__"):
            result = await result
        return str(result)


__all__ = ["NotebookBridge"]
