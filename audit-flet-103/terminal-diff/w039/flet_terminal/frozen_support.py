"""Imperative updates for controls living inside a declarative Flet tree."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["control_update", "thaw"]


@contextmanager
def thaw(control: Any) -> Iterator[None]:
    """Temporarily lift Flet's declarative "frozen" flag from a control.

    Controls that are part of a ``@ft.component`` render tree are stamped
    ``_frozen`` by Flet's object patcher, after which property assignment and
    ``update()`` on them raise ``RuntimeError("Frozen controls cannot be
    updated.")``. Flet performs this exact delete/restore dance internally
    (``base_control._before_update_safe``); this helper lets host apps mutate
    long-lived controls (terminal, key bar, search bar) in place instead of
    forcing a re-render of the owning component.
    """
    if control is None:
        yield
        return
    prev = getattr(control, "_frozen", None)
    if prev is not None:
        object.__delattr__(control, "_frozen")
    try:
        yield
    finally:
        if prev is not None:
            object.__setattr__(control, "_frozen", prev)


def _patch_page(control: Any):
    """Best-effort resolution of the Page that owns ``control``.

    Flet 1.0's declarative reconciler drops the parent chain
    (``_parent`` weakrefs) of every control whose subtree was replaced on
    re-render — visible toggles, lazy mounts, and tab switches all trigger it.
    ``Control.update()`` is dead in that moment because it resolves the page
    by walking dead parent links and raises
    ``Control must be added to the page first``, so callers that gate on
    ``if control.page: control.update()`` silently send nothing to the
    client. The Dart widget keeps the control's logical id while hidden, so
    a patch keyed on that id still lands.
    """
    try:
        # Session-level context var — valid in event handlers, page tasks,
        # effects and component renders.
        from flet import context

        return context.page
    except Exception:
        logger.debug("context.page unavailable for %s", type(control).__name__)
    try:
        return control.page  # walk parent chain; valid while attached
    except Exception:
        logger.debug("parent chain unavailable for %s", type(control).__name__)
        return None


def control_update(control: Any) -> None:
    """Push pending property mutations of ``control`` to the client.

    This is the sanctioned replacement for ``Control.update()`` on
    *frozen* controls in an ``ft.@component`` tree. Call it wrapped in
    ``thaw(control)`` right after mutating properties; it emits the pending
    property diff via the session on the control's stable logical id even
    when the control is detached (hidden tab, lazy container, off-screen
    page), which is the situation where ``control.update()`` is guaranteed
    to either raise ``"Frozen controls cannot be updated."`` or, after the
    reconciler dropped ``_parent``, ``"Control must be added to the page
    first"`` — the two failures previously swallowed by bare ``except
    RuntimeError: pass`` in this package.
    """
    if control is None:
        return
    if getattr(control, "_frozen", None) is not None:
        raise RuntimeError(
            "control_update() on a frozen control — wrap the property "
            "assignment AND this call together in thaw() at the caller."
        )

    page = _patch_page(control)
    if page is None:
        logger.warning(
            "control_update: no page available for %s — change stays local "
            "until the next declarative render.",
            type(control).__name__,
        )
        return

    try:
        page.session.patch_control(control)
    except Exception:
        logger.exception(
            "control_update: patch failed for %s — change stays local.",
            type(control).__name__,
        )
