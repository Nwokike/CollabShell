import flet as ft
from core import tokens
from core.theme import AppColors


def build_notebook_cell(
    page: ft.Page,
    cell: dict,
    on_run=None,
    on_delete=None,
    on_move_up=None,
    on_move_down=None,
    on_change=None,
    on_clear_output=None,
) -> ft.Container:
    """Builds a single notebook cell (Code or Markdown)."""

    cell_type = cell.get("type", "code")
    source = cell.get("source", "")
    outputs = cell.get("outputs", [])
    is_running = cell.get("is_running", False)

    # ── Editor Ref ──
    editor_ref = ft.Ref[ft.TextField]()

    def _handle_change(e):
        if editor_ref.current:
            cell["source"] = editor_ref.current.value
            if on_change:
                on_change()

    async def _copy_output(e):
        text_to_copy = ""
        for out in outputs:
            if out.get("type") == "stream":
                text_to_copy += out.get("text", "") + "\n"
            elif out.get("type") == "error":
                text_to_copy += "\n".join(out.get("traceback", [])) + "\n"
            elif out.get("type") in ["execute_result", "display_data"]:
                data = out.get("data", {})
                if "text/plain" in data:
                    text_to_copy += data["text/plain"] + "\n"
        if text_to_copy:
            await page.clipboard.set(text_to_copy.strip())
            page.snack_bar = ft.SnackBar(ft.Text("Output copied to clipboard!"))
            page.snack_bar.open = True
            page.update()

    # ── Cell Actions ──
    actions_row = ft.Row(
        controls=[
            ft.IconButton(
                ft.Icons.ARROW_UPWARD_ROUNDED,
                icon_size=16,
                tooltip="Move Up",
                on_click=lambda e: on_move_up() if on_move_up else None,
            ),
            ft.IconButton(
                ft.Icons.ARROW_DOWNWARD_ROUNDED,
                icon_size=16,
                tooltip="Move Down",
                on_click=lambda e: on_move_down() if on_move_down else None,
            ),
            ft.IconButton(
                ft.Icons.DELETE_OUTLINE_ROUNDED,
                icon_size=16,
                icon_color=AppColors.ERROR,
                tooltip="Delete Cell",
                on_click=lambda e: on_delete() if on_delete else None,
            ),
        ],
        spacing=0,
    )

    if cell_type == "markdown":
        # ── Markdown Cell ──
        is_editing = cell.get("is_editing", not bool(source.strip()))

        def _toggle_edit(e):
            cell["is_editing"] = not cell.get("is_editing", False)
            if on_change:
                on_change()

        if is_editing:
            content = ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                "Markdown (Edit Mode)",
                                size=tokens.FONT_XS,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                                weight="bold",
                            ),
                            ft.Container(expand=True),
                            ft.FilledButton(
                                "Render",
                                icon=ft.Icons.CHECK_ROUNDED,
                                on_click=_toggle_edit,
                                height=30,
                            ),
                            actions_row,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.TextField(
                        ref=editor_ref,
                        value=source,
                        multiline=True,
                        min_lines=2,
                        max_lines=15,
                        text_size=tokens.FONT_SM,
                        border_color=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
                        bgcolor=ft.Colors.TRANSPARENT,
                        on_change=_handle_change,
                        hint_text="Type markdown here...",
                    ),
                ],
                spacing=tokens.SPACE_SM,
            )
        else:
            content = ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Container(expand=True),
                            ft.IconButton(
                                ft.Icons.EDIT_ROUNDED,
                                icon_size=16,
                                tooltip="Edit Markdown",
                                on_click=_toggle_edit,
                            ),
                        ],
                        visible=False,  # Can make it visible on hover if Flet supported it easily on containers, but we keep it simple for now
                    ),
                    ft.GestureDetector(
                        on_double_tap=_toggle_edit,
                        content=ft.Markdown(
                            source,
                            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                            selectable=True,
                            on_tap_link=lambda e: page.launch_url(e.data),
                        ),
                    ),
                ],
                spacing=0,
            )

        return ft.Container(
            content=content,
            padding=tokens.SPACE_MD,
            border_radius=tokens.RADIUS_MD,
            bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE)
            if is_editing
            else ft.Colors.TRANSPARENT,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE))
            if is_editing
            else None,
            margin=ft.Margin(0, tokens.SPACE_SM, 0, tokens.SPACE_SM),
        )

    else:
        # ── Code Cell ──
        # Outputs rendering
        output_controls = []
        for out in outputs:
            if out.get("type") == "stream":
                is_err = out.get("name") == "stderr"
                output_controls.append(
                    ft.Text(
                        out.get("text", ""),
                        size=tokens.FONT_SM,
                        color=AppColors.ERROR if is_err else "#F8F8F2",
                        font_family="RobotoMono",
                        selectable=True,
                    )
                )
            elif out.get("type") == "error":
                traceback = "\n".join(out.get("traceback", []))
                output_controls.append(
                    ft.Text(
                        traceback,
                        size=tokens.FONT_SM,
                        color=AppColors.ERROR,
                        font_family="RobotoMono",
                        selectable=True,
                    )
                )
            elif out.get("type") in ["execute_result", "display_data"]:
                data = out.get("data", {})
                if "image/png" in data:
                    try:
                        b64_img = data["image/png"]
                        # Sometimes base64 strings have newlines, so we clean them
                        b64_img = b64_img.replace("\n", "").replace("\r", "")
                        output_controls.append(
                            ft.Container(
                                content=ft.Image(
                                    src_base64=b64_img, fit=ft.ImageFit.CONTAIN
                                ),
                                margin=ft.Margin(
                                    0, tokens.SPACE_SM, 0, tokens.SPACE_SM
                                ),
                            )
                        )
                    except Exception as e:
                        output_controls.append(
                            ft.Text(f"Image Error: {e}", color=AppColors.ERROR)
                        )
                elif "text/plain" in data:
                    output_controls.append(
                        ft.Text(
                            data["text/plain"],
                            size=tokens.FONT_SM,
                            color="#F8F8F2",
                            font_family="RobotoMono",
                            selectable=True,
                        )
                    )

        output_actions = ft.Row(
            controls=[
                ft.Text("OUTPUT", size=10, color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE), weight=ft.FontWeight.W_600),
                ft.Row(
                    controls=[
                        ft.IconButton(
                            ft.Icons.COPY_ALL_ROUNDED,
                            icon_size=14,
                            tooltip="Copy Output",
                            on_click=_copy_output,
                        ),
                        ft.IconButton(
                            ft.Icons.CLEAR_ALL_ROUNDED,
                            icon_size=14,
                            tooltip="Clear Output",
                            on_click=lambda e: on_clear_output() if on_clear_output else None,
                        ),
                    ],
                    spacing=0,
                )
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        output_panel = ft.Container(
            content=ft.Column(controls=[output_actions] + output_controls, spacing=2),
            padding=tokens.SPACE_SM,
            bgcolor="#0D0D1A",
            border_radius=tokens.RADIUS_SM,
            visible=len(output_controls) > 0,
            width=float("inf"),
        )

        content = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Container(
                            content=ft.ProgressRing(width=16, height=16, stroke_width=2)
                            if is_running
                            else ft.IconButton(
                                ft.Icons.PLAY_ARROW_ROUNDED,
                                icon_size=20,
                                icon_color=AppColors.SUCCESS,
                                on_click=lambda e: on_run() if on_run else None,
                                tooltip="Run Cell",
                            ),
                            width=40,
                            alignment=ft.Alignment.TOP_CENTER,
                            padding=ft.Padding(0, tokens.SPACE_SM, 0, 0),
                        ),
                        ft.Container(
                            content=ft.TextField(
                                ref=editor_ref,
                                value=source,
                                multiline=True,
                                min_lines=1,
                                max_lines=25,
                                text_style=ft.TextStyle(font_family="RobotoMono", size=tokens.FONT_SM),
                                border_color=ft.Colors.TRANSPARENT,
                                bgcolor=ft.Colors.with_opacity(
                                    0.03, ft.Colors.ON_SURFACE
                                ),
                                on_change=_handle_change,
                                hint_text="Code...",
                                content_padding=tokens.SPACE_SM,
                                border_radius=tokens.RADIUS_SM,
                            ),
                            expand=True,
                        ),
                        actions_row,
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                ft.Container(
                    content=output_panel,
                    padding=ft.Padding(
                        48, 0, 0, 0
                    ),  # Indent outputs to align with textfield
                ),
            ],
            spacing=tokens.SPACE_XS,
        )

        return ft.Container(
            content=content,
            padding=ft.Padding(0, tokens.SPACE_SM, tokens.SPACE_SM, tokens.SPACE_SM),
            border=ft.Border(
                left=ft.BorderSide(3, ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE))
            ),
            margin=ft.Margin(0, tokens.SPACE_SM, 0, tokens.SPACE_SM),
        )
