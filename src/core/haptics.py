"""One-shot haptic feedback; the service auto-registers on first use."""

from __future__ import annotations

import logging

import flet as ft

logger = logging.getLogger(__name__)

_service: ft.HapticFeedback | None = None


async def buzz(kind: str = "medium") -> None:
    """Fire a `{kind}_impact` haptic; silent no-op where unsupported."""
    global _service
    try:
        if _service is None:
            _service = ft.HapticFeedback()
        await getattr(_service, f"{kind}_impact")()
    except Exception:
        logger.debug("Haptic feedback unavailable", exc_info=True)
