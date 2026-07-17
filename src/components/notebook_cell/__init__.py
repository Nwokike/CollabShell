import flet as ft
from core import tokens
from core.theme import AppColors
from components.notebook_cell.actions import make_actions_row, copy_output
from components.notebook_cell.output import parse_outputs_to_controls


def build_notebook_cell(
    page: ft.Page,
    cell: dict,
    on_run=None,
    on_stop=None,
    on_delete=None,
    on_move_up=None,
    on_move_down=None,
    on_change=None,
    on_clear_output=None,
    on_open_terminal=None,
) -> tuple[ft.Container, dict]:
    """Builds a single notebook cell (Code or Markdown).

    Returns (container, refs_dict) where refs_dict holds Ref objects
    for mutable parts of the cell (play_btn, stop_row, output).
    """
    cell_type = cell.get("type", "code")
    source = cell.get("source", "")
    outputs = cell.get("outputs", [])
    is_running = cell.get("is_running", False)

    editor_ref = ft.Ref[ft.TextField]()
    play_btn_ref = ft.Ref[ft.IconButton]()
    stop_row_ref = ft.Ref[ft.Row]()
    output_ref = ft.Ref[ft.ListView]()

    refs = {
        "play_btn": play_btn_ref,
        "stop_row": stop_row_ref,
        "output": output_ref,
        "code_input": editor_ref,
    }

    def _handle_change(e):
        if editor_ref.current:
            cell["source"] = editor_ref.current.value
            if on_change:
                on_change()

    async def _copy_output(e):
        await copy_output(page, outputs)

    def _make_actions_row():
        return make_actions_row(on_move_up, on_move_down, on_delete)

    if cell_type == "markdown":
        is_editing_initial = cell.get("is_editing", not bool(source.strip()))
        edit_container = ft.Container(visible=is_editing_initial)
        render_container = ft.Container(visible=not is_editing_initial)
        markdown_ref = ft.Ref[ft.Markdown]()

        def _edit(e=None):
            if not cell.get("is_editing"):
                cell["is_editing"] = True
                edit_container.visible = True
                render_container.visible = False
                if on_change:
                    on_change()
                page.update()

        def _render(e=None):
            if cell.get("is_editing"):
                if editor_ref.current:
                    cell["source"] = editor_ref.current.value
                    if markdown_ref.current:
                        markdown_ref.current.value = cell["source"]
                cell["is_editing"] = False
                edit_container.visible = False
                render_container.visible = True
                if on_change:
                    on_change()
                page.update()

        edit_container.content = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.TextField(
                            ref=editor_ref,
                            value=source,
                            multiline=True,
                            min_lines=2,
                            max_lines=8,
                            text_size=tokens.FONT_SM,
                            border_color=ft.Colors.TRANSPARENT,
                            bgcolor=ft.Colors.TRANSPARENT,
                            on_change=_handle_change,
                            on_blur=_render,
                            hint_text="Type markdown here...",
                            content_padding=tokens.SPACE_SM,
                            expand=True,
                        ),
                    ],
                ),
                ft.Row(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.MODE_EDIT_OUTLINE_ROUNDED,
                                    size=tokens.FONT_MD,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Text(
                                    "Markdown",
                                    size=tokens.FONT_XS,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                    weight=ft.FontWeight.W_600,
                                ),
                            ],
                            spacing=tokens.SPACE_XS,
                        ),
                        ft.Container(expand=True),
                        ft.FilledButton(
                            "Render",
                            icon=ft.Icons.CHECK_ROUNDED,
                            on_click=_render,
                            height=tokens.SPACE_LG * 2,
                            style=ft.ButtonStyle(padding=ft.Padding(12, 0, 12, 0)),
                        ),
                        _make_actions_row(),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=0,
        )

        render_container.content = ft.Column(
            controls=[
                ft.GestureDetector(
                    on_tap=_edit,
                    content=ft.Container(
                        content=ft.Markdown(
                            ref=markdown_ref,
                            value=source,
                            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                            selectable=True,
                            on_tap_link=lambda e: page.run_task(
                                ft.UrlLauncher().launch_url, e.data
                            ),
                        ),
                        padding=tokens.SPACE_SM,
                        expand=True,
                        width=float("inf"),
                    ),
                ),
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Container(expand=True),
                            ft.IconButton(
                                ft.Icons.EDIT_ROUNDED,
                                icon_size=tokens.ICON_SM,
                                tooltip="Edit Markdown",
                                on_click=_edit,
                            ),
                            _make_actions_row(),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                    padding=ft.Padding(
                        tokens.SPACE_SM, 0, tokens.SPACE_SM, tokens.SPACE_SM
                    ),
                ),
            ],
            spacing=0,
        )

        content = ft.Column([edit_container, render_container], spacing=0)

        return ft.Container(
            content=content,
            border_radius=tokens.RADIUS_MD,
            bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)),
            margin=ft.Margin(0, tokens.SPACE_SM, 0, tokens.SPACE_SM),
        ), refs

    # ── Code Cell ──
    output_controls = parse_outputs_to_controls(outputs)

    output_actions = ft.Row(
        controls=[
            ft.Text(
                "OUTPUT",
                size=tokens.FONT_XXS,
                color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                weight=ft.FontWeight.W_600,
            ),
            ft.Row(
                controls=[
                    ft.IconButton(
                        ft.Icons.TERMINAL_ROUNDED,
                        icon_size=tokens.ICON_SM,
                        tooltip="Open Real Terminal",
                        on_click=lambda e: (
                            on_open_terminal() if on_open_terminal else None
                        ),
                    ),
                    ft.IconButton(
                        ft.Icons.COPY_ALL_ROUNDED,
                        icon_size=tokens.ICON_SM,
                        tooltip="Copy Output",
                        on_click=_copy_output,
                    ),
                    ft.IconButton(
                        ft.Icons.CLEAR_ALL_ROUNDED,
                        icon_size=tokens.ICON_SM,
                        tooltip="Clear Output",
                        on_click=lambda e: (
                            on_clear_output() if on_clear_output else None
                        ),
                    ),
                ],
                spacing=0,
            ),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    output_panel = ft.Container(
        content=ft.Column(
            controls=[
                ft.ListView(
                    ref=output_ref,
                    controls=output_controls,
                    spacing=tokens.SPACE_XXS,
                    auto_scroll=True,
                    height=tokens.SPACE_XXXL * 8,
                    expand=False,
                ),
                output_actions,
            ],
            spacing=tokens.SPACE_XXS,
        ),
        padding=tokens.SPACE_SM,
        bgcolor=AppColors.TERMINAL_BG,
        border_radius=tokens.RADIUS_SM,
        visible=True,
        width=float("inf"),
    )

    play_button = ft.IconButton(
        ft.Icons.PLAY_ARROW_ROUNDED,
        ref=play_btn_ref,
        icon_size=tokens.ICON_MD,
        icon_color=AppColors.SUCCESS,
        on_click=lambda e: on_run() if on_run else None,
        tooltip="Run Cell",
        visible=not is_running,
    )

    stop_row = ft.Row(
        ref=stop_row_ref,
        controls=[
            ft.ProgressRing(
                width=tokens.ICON_SM,
                height=tokens.ICON_SM,
                stroke_width=2,
            ),
            ft.IconButton(
                ft.Icons.STOP_ROUNDED,
                icon_size=tokens.ICON_SM,
                icon_color=AppColors.ERROR,
                on_click=lambda e: on_stop() if on_stop else None,
                tooltip="Stop",
            ),
        ],
        spacing=tokens.SPACE_XS,
        visible=is_running,
    )

    unified_editor_box = ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.TextField(
                            ref=editor_ref,
                            value=source,
                            multiline=True,
                            min_lines=1,
                            max_lines=10,
                            text_style=ft.TextStyle(
                                font_family="RobotoMono", size=tokens.FONT_SM
                            ),
                            border_color=ft.Colors.TRANSPARENT,
                            bgcolor=ft.Colors.TRANSPARENT,
                            on_change=_handle_change,
                            hint_text="Write Python code here.\nPrefix with ! to run a terminal command\ne.g. !pip install requests",
                            content_padding=tokens.SPACE_SM,
                            expand=True,
                        ),
                    ],
                ),
                ft.Container(
                    content=ft.Row(
                        controls=[
                            play_button,
                            stop_row,
                            ft.Container(expand=True),
                            _make_actions_row(),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding(
                        tokens.SPACE_XS, 0, tokens.SPACE_SM, tokens.SPACE_XS
                    ),
                ),
            ],
            spacing=0,
        ),
        border_radius=tokens.RADIUS_SM,
        bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
    )

    content = ft.Column(
        controls=[
            unified_editor_box,
            ft.Container(
                content=output_panel,
                padding=ft.Padding(0, tokens.SPACE_XS, 0, 0),
            ),
        ],
        spacing=0,
    )

    container = ft.Container(
        content=content,
        padding=tokens.SPACE_SM,
        border=ft.Border(
            left=ft.BorderSide(3, ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE)),
        ),
        margin=ft.Margin(0, tokens.SPACE_SM, 0, tokens.SPACE_SM),
    )

    return container, refs
