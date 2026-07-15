import flet as ft

from core import tokens
from core.theme import AppColors
from components.ansi_parser import parse_ansi_to_flet_text

# Try to import FletXterm, fall back to text-based output if not available
try:
    from flet_xterm import FletXterm

    XTERM_AVAILABLE = True
except ImportError:
    XTERM_AVAILABLE = False


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
) -> tuple[ft.Container, dict]:
    """Builds a single notebook cell (Code or Markdown).

    Returns (container, refs_dict) where refs_dict holds Ref objects
    for mutable parts of the cell (play_btn, stop_row, output, terminal).
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
        "terminal": None,  # Will hold FletXterm instance if available
        "initial_text": "",  # Replayed into the terminal before each run
    }

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
            await ft.Clipboard().set(text_to_copy.strip())
            page.show_dialog(
                ft.SnackBar(ft.Text("Output copied to clipboard!"))
            )

    # ── Cell Actions ──
    # A Flutter control can only have a single parent, so build a fresh
    # instance wherever the actions are needed (markdown edit, markdown
    # render, and code cells would otherwise attempt to share one control).
    def _make_actions_row():
        return ft.Row(
            controls=[
                ft.IconButton(
                    ft.Icons.ARROW_UPWARD_ROUNDED,
                    icon_size=tokens.ICON_SM,
                    tooltip="Move Up",
                    on_click=lambda e: on_move_up() if on_move_up else None,
                ),
                ft.IconButton(
                    ft.Icons.ARROW_DOWNWARD_ROUNDED,
                    icon_size=tokens.ICON_SM,
                    tooltip="Move Down",
                    on_click=lambda e: on_move_down() if on_move_down else None,
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE_ROUNDED,
                    icon_size=tokens.ICON_SM,
                    icon_color=AppColors.ERROR,
                    tooltip="Delete Cell",
                    on_click=lambda e: on_delete() if on_delete else None,
                ),
            ],
            spacing=0,
        )

    if cell_type == "markdown":
        # ── Markdown Cell (unchanged) ──
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
                            max_lines=15,
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
                            height=28,
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
                            on_tap_link=lambda e: page.launch_url(e.data),
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

    # Build terminal or text-based output
    # The FletXterm custom control is compiled into the Android build.
    # On a desktop dev server (or if xterm is unavailable) we fall back to
    # text-based ANSI output.
    is_supported_platform = page.platform.is_mobile() if page.platform else False

    if XTERM_AVAILABLE and is_supported_platform:
        terminal = FletXterm(
            theme_name="defaultTheme",
            cursor_type="block",
            font_size=13,
            font_family="monospace",
            read_only=False,
            max_lines=5000,
            background_opacity=1.0,
            height=200,
            expand=False,
        )
        refs["terminal"] = terminal

        # Replay existing outputs into terminal
        initial_text = ""
        for out in outputs:
            if out.get("type") == "stream":
                text = out.get("text", "")
                initial_text += text.replace("\n", "\r\n")
            elif out.get("type") == "error":
                traceback = "\n".join(out.get("traceback", []))
                initial_text += traceback.replace("\n", "\r\n")
            elif out.get("type") in ["execute_result", "display_data"]:
                data = out.get("data", {})
                if "text/plain" in data:
                    initial_text += data["text/plain"].replace("\n", "\r\n")
        if initial_text:
            refs["initial_text"] = initial_text

        output_actions = ft.Row(
            controls=[
                ft.Text(
                    "TERMINAL",
                    size=tokens.FONT_XXS,
                    color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE),
                    weight=ft.FontWeight.W_600,
                ),
                ft.Row(
                    controls=[
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
                ref=output_ref,
                controls=[terminal, output_actions],
                spacing=tokens.SPACE_XXS,
            ),
            padding=tokens.SPACE_SM,
            bgcolor=AppColors.TERMINAL_BG,
            border_radius=tokens.RADIUS_SM,
            visible=True,
            width=float("inf"),
        )
    else:
        # Fallback: text-based output (original behavior)
        output_controls = []
        for out in outputs:
            if len(output_controls) >= 1000:
                break
            if out.get("type") == "stream":
                is_err = out.get("name") == "stderr"
                text = out.get("text", "")
                output_controls.append(
                    parse_ansi_to_flet_text(
                        raw_text=text, default_size=tokens.FONT_SM, is_error=is_err
                    )
                )
            elif out.get("type") == "error":
                traceback = "\n".join(out.get("traceback", []))
                output_controls.append(
                    parse_ansi_to_flet_text(
                        raw_text=traceback,
                        default_size=tokens.FONT_SM,
                        is_error=True,
                    )
                )
            elif out.get("type") in ["execute_result", "display_data"]:
                data = out.get("data", {})
                if "image/png" in data:
                    try:
                        b64_img = data["image/png"]
                        b64_img = b64_img.replace("\n", "").replace("\r", "")
                        output_controls.append(
                            ft.Container(
                                content=ft.Image(
                                    src_base64=b64_img, fit=ft.BoxFit.CONTAIN
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
                        parse_ansi_to_flet_text(
                            raw_text=data["text/plain"],
                            default_size=tokens.FONT_SM,
                        )
                    )

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
                        height=320,
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
                            max_lines=25,
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
