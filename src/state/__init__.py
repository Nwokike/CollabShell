"""App state context — component-facing adapter over the observable state."""

from __future__ import annotations

import flet as ft

from core.state import state
from state.controller_ctx import ControllerMethods, ControllerMethodsCtx
from state.service_ctx import ServiceCtx, Services

AppStateCtx = ft.create_context(state)

__all__ = [
    "AppStateCtx",
    "ControllerMethods",
    "ControllerMethodsCtx",
    "ServiceCtx",
    "Services",
    "state",
]
