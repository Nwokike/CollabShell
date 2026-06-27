"""File item — reusable list item for the file browser."""

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


def _format_size(size_bytes) -> str:
    """Format file size to human-readable string."""
    if size_bytes is None or size_bytes == 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return (
                f"{size_bytes:.0f} {unit}"
                if unit == "B"
                else f"{size_bytes:.1f} {unit}"
            )
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def build_file_item(
    file_info: dict,
    on_click=None,
    on_delete=None,
) -> ft.Container:
    """Build a file browser list item.

    file_info dict: name, type ("directory" | "file"), size
    """
    name = file_info.get("name", "")
    is_dir = file_info.get("type") == "directory"
    size = file_info.get("size", 0)

    icon = _file_icon(name, is_dir)

    return ft.Container(
        content=ft.Row(
            controls=[
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
                            weight=ft.FontWeight.W_500
                            if is_dir
                            else ft.FontWeight.W_400,
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
                ft.Icon(
                    ft.Icons.CHEVRON_RIGHT_ROUNDED
                    if is_dir
                    else ft.Icons.MORE_VERT_ROUNDED,
                    size=tokens.ICON_MD,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_MD,
        ),
        padding=ft.Padding(
            tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_MD
        ),
        on_click=on_click,
        ink=True,
    )
