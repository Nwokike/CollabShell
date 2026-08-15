"""Service context — exposes backend services to the component tree.

Components read services via ``ft.use_context(ServiceCtx)`` instead of
receiving them as constructor parameters.
"""

from __future__ import annotations

from dataclasses import dataclass

import flet as ft


@dataclass
class Services:
    """Subset of backend service instances available to the UI."""

    colab: object = None
    storage: object = None
    ad_service: object = None
    page: object = None  # ft.Page ref for services that need it directly


ServiceCtx = ft.create_context(Services())

__all__ = ["ServiceCtx", "Services"]
