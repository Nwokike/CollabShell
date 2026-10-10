"""ExtraKeysBar — virtual accessory keyboard and settings toolbar for FletTerminal."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

import flet as ft

from .frozen_support import control_update, thaw
from .tokens import (
    BTN_FONT_SIZE,
    BTN_HEIGHT,
    COLOR_ACTIVE_BG,
    COLOR_ACTIVE_FG,
    COLOR_INACTIVE_BG,
    COLOR_INACTIVE_FG,
    SPACE_XS,
)

logger = logging.getLogger(__name__)

__all__ = ["DEFAULT_EXTRA_KEYS", "ExtraKeysBar"]


# Reactive modifier state. Flet 0.86's declarative model only repaints a control
# when its owning @ft.component re-renders (it diffs the previous render tree
# against the new one). Mutating `style` + `update()` is a no-op there, so the
# CTRL/ALT "light" is driven by this observable: the buttons subscribe to it and
# re-render whenever a flag flips.
@ft.observable
@dataclass
class ModifierState:
    """Sticky CTRL/ALT state shared between ExtraKeysBar logic and the buttons."""

    ctrl: bool = False
    alt: bool = False


def _modifier_style(active: bool) -> ft.ButtonStyle:
    return ft.ButtonStyle(
        padding=ft.Padding.symmetric(horizontal=6, vertical=0),
        bgcolor=COLOR_ACTIVE_BG if active else COLOR_INACTIVE_BG,
        color=COLOR_ACTIVE_FG if active else COLOR_INACTIVE_FG,
        visual_density=ft.VisualDensity.COMPACT,
        side=ft.BorderSide(width=0),
    )


@ft.component
def ModifierKey(state: ModifierState, label: str, on_toggle: Callable[[], None]):
    """A single CTRL/ALT toggle rendered reactively from `state`.

    Subscribing to `state` via `use_state` makes this component re-render (and
    repaint the button) the moment `state.ctrl`/`state.alt` changes — whether
    the change came from a tap here or from `reset_modifiers()` on the bar.
    """
    st, _ = ft.use_state(state)
    which = label.lower()
    active = getattr(st, which)
    return ft.Button(
        content=ft.Text(label, size=BTN_FONT_SIZE, weight=ft.FontWeight.BOLD),
        height=BTN_HEIGHT,
        style=_modifier_style(active),
        on_click=lambda e: on_toggle(),
    )


DEFAULT_EXTRA_KEYS: list[tuple[str, bytes | None]] = [
    ("ESC", b"\x1b"),
    ("TAB", b"\t"),
    ("CTRL", None),
    ("ALT", None),
    ("↑", b"\x1b[A"),
    ("↓", b"\x1b[B"),
    ("←", b"\x1b[D"),
    ("→", b"\x1b[C"),
    ("-", b"-"),
    ("/", b"/"),
    ("|", b"|"),
    ("~", b"~"),
    ("^", b"^"),
]


class ExtraKeysBar(ft.Container):
    """Virtual toolbar displaying quick keys, sticky modifier toggles, and settings."""

    def __init__(
        self,
        on_send_payload: Callable[[bytes], None],
        on_modifier_change: Callable[[bool, bool], None],
        show_settings: bool = True,
        on_set_theme: Callable[[str], None] | None = None,
        on_set_cursor: Callable[[str], None] | None = None,
        on_toggle_blink: Callable[[], None] | None = None,
        on_toggle_search: Callable[[], None] | None = None,
        on_copy: Callable[[], None] | None = None,
        on_paste: Callable[[], None] | None = None,
        on_select_all: Callable[[], None] | None = None,
        on_clear: Callable[[], None] | None = None,
        keys: list[tuple[str, bytes | None]] | None = None,
    ):
        self._on_send_payload = on_send_payload
        self._on_modifier_change = on_modifier_change
        self._on_set_theme = on_set_theme
        self._on_set_cursor = on_set_cursor
        self._on_toggle_blink = on_toggle_blink
        self._on_toggle_search = on_toggle_search
        self._on_copy = on_copy
        self._on_paste = on_paste
        self._on_select_all = on_select_all
        self._on_clear = on_clear
        self._keys = keys or DEFAULT_EXTRA_KEYS

        self._mods = ModifierState()
        self._collapsed = False

        self.active_theme = "JetBrains Dark"
        self.active_cursor = "block"
        self.active_blink = True
        self.active_search = True
        self.current_font_size = 11.0
        self.default_font_size = 11.0
        self._on_zoom_in: Callable[[], None] | None = None
        self._on_zoom_out: Callable[[], None] | None = None
        self._on_zoom_reset: Callable[[], None] | None = None

        self._btn_ctrl: ft.Button | None = None
        self._btn_alt: ft.Button | None = None

        self._toggle_btn = ft.IconButton(
            icon=ft.Icons.ARROW_DROP_UP,
            icon_size=20,
            tooltip="Hide keys",
            style=ft.ButtonStyle(padding=2, visual_density=ft.VisualDensity.COMPACT),
            on_click=self._on_toggle_collapse,
        )

        key_controls: list[ft.Control] = []
        if show_settings:
            key_controls.append(self._build_settings_menu())

        for label, payload in self._keys:
            key_controls.append(self._make_key_btn(label, payload))

        self._keys_row = ft.Row(
            controls=key_controls,
            spacing=SPACE_XS,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        self._expanded_row = ft.Row(
            controls=[
                self._toggle_btn,
                self._keys_row,
            ],
            spacing=2,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self._collapsed_view = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(expand=True),
                    self._toggle_btn,
                    ft.Container(expand=True),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=self._on_toggle_collapse,
            ink=True,
            tooltip="Click anywhere to show keys",
        )

        super().__init__(
            content=self._expanded_row,
            padding=ft.Padding(4, 1, 4, 1),
            bgcolor="#181825",
        )

    # Backwards-compatible accessors. MobileTerminal assigns these (e.g. from
    # the Dart `modifier_reset` event); routing them through the observable
    # keeps the on-screen buttons in sync via their reactive subscription.
    @property
    def ctrl_active(self) -> bool:
        return self._mods.ctrl

    @ctrl_active.setter
    def ctrl_active(self, value: bool):
        self._mods.ctrl = bool(value)

    @property
    def alt_active(self) -> bool:
        return self._mods.alt

    @alt_active.setter
    def alt_active(self, value: bool):
        self._mods.alt = bool(value)

    def _get_settings_menu_items(self) -> list[ft.Control]:
        """Return the refreshed list of items with current checkmarks and font size."""
        return [
            ft.PopupMenuItem(
                content=ft.Text("Clipboard", weight=ft.FontWeight.BOLD),
                disabled=True,
            ),
            ft.PopupMenuItem(
                content=ft.Text("Copy Selection"),
                icon=ft.Icons.COPY_ROUNDED,
                on_click=lambda e: self._on_copy() if self._on_copy else None,
            ),
            ft.PopupMenuItem(
                content=ft.Text("Paste"),
                icon=ft.Icons.CONTENT_PASTE_ROUNDED,
                on_click=lambda e: self._on_paste() if self._on_paste else None,
            ),
            ft.PopupMenuItem(
                content=ft.Text("Select All"),
                icon=ft.Icons.SELECT_ALL_ROUNDED,
                on_click=lambda e: (
                    self._on_select_all() if self._on_select_all else None
                ),
            ),
            ft.PopupMenuItem(
                content=ft.Text("Clear Terminal"),
                icon=ft.Icons.CLEAR_ALL_ROUNDED,
                on_click=lambda e: self._on_clear() if self._on_clear else None,
            ),
            ft.PopupMenuItem(),
            ft.PopupMenuItem(
                content=ft.Text("Theme Presets", weight=ft.FontWeight.BOLD),
                disabled=True,
            ),
            ft.PopupMenuItem(
                content=ft.Text("Dracula"),
                checked=self.active_theme == "Dracula",
                on_click=lambda e: (
                    self._on_set_theme("Dracula") if self._on_set_theme else None
                ),
            ),
            ft.PopupMenuItem(
                content=ft.Text("JetBrains Dark"),
                checked=self.active_theme == "JetBrains Dark",
                on_click=lambda e: (
                    self._on_set_theme("JetBrains Dark") if self._on_set_theme else None
                ),
            ),
            ft.PopupMenuItem(
                content=ft.Text("Matrix Green"),
                checked=self.active_theme == "Matrix Green",
                on_click=lambda e: (
                    self._on_set_theme("Matrix Green") if self._on_set_theme else None
                ),
            ),
            ft.PopupMenuItem(
                content=ft.Text("Colab Light"),
                checked=self.active_theme == "Colab Light",
                on_click=lambda e: (
                    self._on_set_theme("Colab Light") if self._on_set_theme else None
                ),
            ),
            ft.PopupMenuItem(),
            ft.PopupMenuItem(
                content=ft.Text("Font Size / Zoom", weight=ft.FontWeight.BOLD),
                disabled=True,
            ),
            ft.PopupMenuItem(
                content=ft.Text("Zoom In (+)"),
                on_click=lambda e: self._on_zoom_in() if self._on_zoom_in else None,
            ),
            ft.PopupMenuItem(
                content=ft.Text("Zoom Out (-)"),
                on_click=lambda e: self._on_zoom_out() if self._on_zoom_out else None,
            ),
            ft.PopupMenuItem(
                content=ft.Text(f"Reset Zoom ({int(self.default_font_size)}px)"),
                on_click=lambda e: (
                    self._on_zoom_reset() if self._on_zoom_reset else None
                ),
            ),
            ft.PopupMenuItem(),
            ft.PopupMenuItem(
                content=ft.Text("Toggle Options", weight=ft.FontWeight.BOLD),
                disabled=True,
            ),
            ft.PopupMenuItem(
                content=ft.Text("Cursor Blink"),
                checked=self.active_blink,
                on_click=lambda e: (
                    self._on_toggle_blink() if self._on_toggle_blink else None
                ),
            ),
            ft.PopupMenuItem(
                content=ft.Text("Search Bar"),
                checked=self.active_search,
                on_click=lambda e: (
                    self._on_toggle_search() if self._on_toggle_search else None
                ),
            ),
        ]

    def _build_settings_menu(self) -> ft.PopupMenuButton:
        self._settings_menu = ft.PopupMenuButton(
            icon=ft.Icons.SETTINGS,
            icon_size=16,
            tooltip="Terminal Settings",
            style=ft.ButtonStyle(padding=2, visual_density=ft.VisualDensity.COMPACT),
            items=self._get_settings_menu_items(),
        )
        return self._settings_menu

    def update_settings_menu(self):
        """Refresh the items and checkmarks inside the settings menu."""
        if hasattr(self, "_settings_menu") and self._settings_menu:
            with thaw(self._settings_menu):
                self._settings_menu.items = self._get_settings_menu_items()
                control_update(self._settings_menu)

    def _make_key_btn(self, label: str, payload: bytes | None) -> ft.Control:
        if payload is None:
            is_ctrl = label == "CTRL"
            btn = ModifierKey(
                self._mods,
                label,
                lambda: self._toggle_modifier(is_ctrl),
            )
            if is_ctrl:
                self._btn_ctrl = btn
            else:
                self._btn_alt = btn
            return btn

        return ft.Button(
            content=ft.Text(
                label,
                size=BTN_FONT_SIZE,
                weight=ft.FontWeight.BOLD,
                color=COLOR_INACTIVE_FG,
            ),
            height=BTN_HEIGHT,
            style=ft.ButtonStyle(
                padding=ft.Padding.symmetric(horizontal=6, vertical=0),
                bgcolor=COLOR_INACTIVE_BG,
                visual_density=ft.VisualDensity.COMPACT,
                side=ft.BorderSide(width=0),
            ),
            on_click=lambda e, p=payload: self._send_payload(p),
        )

    def _toggle_modifier(self, is_ctrl: bool):
        if is_ctrl:
            self._mods.ctrl = not self._mods.ctrl
        else:
            self._mods.alt = not self._mods.alt
        # The button repaints via its reactive subscription to `self._mods`;
        # no imperative style/update is needed (or even effective) here.
        self._on_modifier_change(self._mods.ctrl, self._mods.alt)

    def reset_modifiers(self):
        if self._mods.ctrl or self._mods.alt:
            self._mods.ctrl = False
            self._mods.alt = False
            self._on_modifier_change(self._mods.ctrl, self._mods.alt)

    def _send_payload(self, payload: bytes):
        if self._mods.ctrl and len(payload) == 1:
            code = payload[0]
            if 97 <= code <= 122:
                payload = bytes([code - 96])
            elif 65 <= code <= 90:
                payload = bytes([code - 64])
            self._mods.ctrl = False
            self._on_modifier_change(self._mods.ctrl, self._mods.alt)
        if self._mods.alt:
            payload = b"\x1b" + payload
            self._mods.alt = False
            self._on_modifier_change(self._mods.ctrl, self._mods.alt)
        self._on_send_payload(payload)

    def _on_toggle_collapse(self, e):
        self._collapsed = not self._collapsed
        with thaw(self._toggle_btn):
            if self._collapsed:
                self._toggle_btn.icon = ft.Icons.ARROW_DROP_DOWN
                self._toggle_btn.tooltip = "Show keys"
            else:
                self._toggle_btn.icon = ft.Icons.ARROW_DROP_UP
                self._toggle_btn.tooltip = "Hide keys"
        with thaw(self):
            self.content = (
                self._collapsed_view if self._collapsed else self._expanded_row
            )
            control_update(self)
