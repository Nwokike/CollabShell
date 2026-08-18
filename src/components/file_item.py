"""File item — reusable list item for the file browser matching SpanInsight."""

from __future__ import annotations

import flet as ft

from core import tokens


def _file_icon(name: str, is_dir: bool) -> ft.Icons:
    """Return an appropriate icon based on file type."""
    if is_dir:
        return ft.Icons.FOLDER_ROUNDED
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    icon_map = {
        "py": ft.Icons.CODE_ROUNDED,
        "ipynb": ft.Icons.BOOK_ROUNDED,
        "csv": ft.Icons.TABLE_CHART_ROUNDED,
        "json": ft.Icons.DATA_OBJECT_ROUNDED,
        "txt": ft.Icons.DESCRIPTION_ROUNDED,
        "md": ft.Icons.ARTICLE_ROUNDED,
        "png": ft.Icons.IMAGE_ROUNDED,
        "jpg": ft.Icons.IMAGE_ROUNDED,
        "jpeg": ft.Icons.IMAGE_ROUNDED,
        "pdf": ft.Icons.PICTURE_AS_PDF_ROUNDED,
        "zip": ft.Icons.FOLDER_ZIP_ROUNDED,
        "tar": ft.Icons.FOLDER_ZIP_ROUNDED,
        "gz": ft.Icons.FOLDER_ZIP_ROUNDED,
        "h5": ft.Icons.STORAGE_ROUNDED,
        "pkl": ft.Icons.STORAGE_ROUNDED,
        "pt": ft.Icons.STORAGE_ROUNDED,
        "bin": ft.Icons.STORAGE_ROUNDED,
    }
    return icon_map.get(ext, ft.Icons.INSERT_DRIVE_FILE_ROUNDED)


def _format_size(size_bytes: float | None) -> str:
    """Format file size to human-readable string."""
    if size_bytes is None or size_bytes == 0:
        return ""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def build_file_item(
    file_info: dict | None = None,
    item: dict | None = None,
    selected: bool = False,
    is_selected: bool = False,
    selection_mode: bool = False,
    on_click=None,
    on_tap=None,
    on_long_press=None,
) -> ft.Container:
    """Build a file browser list item matching SpanInsight's visual style."""
    data = file_info or item or {}
    name = data.get("name", "")
    is_dir = data.get("type") == "directory" or data.get("is_dir", False)
    size = data.get("size", 0)

    is_sel = selected or is_selected
    click_fn = on_click or on_tap

    icon = _file_icon(name, is_dir)

    controls: list[ft.Control] = [
        ft.Icon(
            icon,
            size=tokens.ICON_LG,
            color=ft.Colors.PRIMARY if is_dir else ft.Colors.ON_SURFACE_VARIANT,
        ),
        ft.Column(
            controls=[
                ft.Text(
                    name,
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.W_500 if is_dir else ft.FontWeight.W_400,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                ft.Text(
                    _format_size(size) if not is_dir else "Folder",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=tokens.SPACE_XXS,
            expand=True,
        ),
    ]

    # Show selection checkbox/radio when in selection mode
    if selection_mode or is_sel:
        controls.append(
            ft.Icon(
                ft.Icons.CHECK_CIRCLE_ROUNDED
                if is_sel
                else ft.Icons.RADIO_BUTTON_UNCHECKED,
                size=tokens.ICON_MD,
                color=ft.Colors.PRIMARY if is_sel else ft.Colors.ON_SURFACE_VARIANT,
            )
        )

    return ft.Container(
        bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY)
        if is_sel
        else ft.Colors.TRANSPARENT,
        border_radius=tokens.RADIUS_MD,
        content=ft.Row(
            controls=controls,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_MD,
        ),
        padding=ft.Padding(
            tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_MD
        ),
        on_click=click_fn,
        on_long_press=on_long_press,
        ink=True,
    )
