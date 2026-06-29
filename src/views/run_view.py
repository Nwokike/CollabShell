"""Quick Run view — one-shot script execution (colab run equivalent)."""

from __future__ import annotations

import time
import flet as ft

from core import tokens, constants
from core.styles import section_header, tip_text, build_banner_ad, glass_card
from components.output_panel import build_output_panel


def build_run_view(
    page: ft.Page,
    colab_service,
    state,
    on_back=None,
    snack=None,
    theme_btn=None,
) -> ft.View:
    """Build the Quick Run view for one-shot script execution."""

    script_path_ref = ft.Ref[ft.TextField]()
    args_ref = ft.Ref[ft.TextField]()
    session_name_ref = ft.Ref[ft.TextField]()
    gpu_ref = ft.Ref[ft.Dropdown]()
    tpu_ref = ft.Ref[ft.Dropdown]()
    timeout_ref = ft.Ref[ft.Dropdown]()
    keep_ref = ft.Ref[ft.Switch]()
    output_lines = []
    output_list_ref = ft.Ref[ft.ListView]()
    _last_output_update = 0.0
    is_running = False
    run_btn_ref = ft.Ref[ft.FilledButton]()

    file_picker = getattr(page, "file_picker", None)

    def _on_file_picked(e: ft.FilePickerResultEvent):
        if page.route != "/run":
            return
        if e.files and script_path_ref.current:
            script_path_ref.current.value = e.files[0].path
            page.update()

    if file_picker:
        file_picker.on_result = _on_file_picked

    async def _on_browse_click(e):
        if file_picker:
            await file_picker.pick_files(
                allowed_extensions=["py"],
                dialog_title="Select Python Script",
            )

    hardware_type = "CPU"

    def _on_hardware_change(e):
        nonlocal hardware_type
        selected = e.control.selected
        if selected:
            hardware_type = list(selected)[0]
        if gpu_ref.current:
            gpu_ref.current.visible = hardware_type == "GPU"
        if tpu_ref.current:
            tpu_ref.current.visible = hardware_type == "TPU"
        page.update()

    async def _on_run(e):
        nonlocal is_running
        script = (
            script_path_ref.current.value.strip() if script_path_ref.current else ""
        )
        if not script:
            if snack:
                snack("Please select a script file")
            return

        args_str = args_ref.current.value.strip() if args_ref.current else ""
        args = args_str.split() if args_str else []
        sess_name = (
            session_name_ref.current.value.strip() if session_name_ref.current else None
        )
        gpu = None
        tpu = None
        if hardware_type == "GPU" and gpu_ref.current:
            gpu = gpu_ref.current.value
        elif hardware_type == "TPU" and tpu_ref.current:
            tpu = tpu_ref.current.value
        keep = keep_ref.current.value if keep_ref.current else False
        timeout_val = (
            float(timeout_ref.current.value)
            if timeout_ref.current and timeout_ref.current.value
            else 30.0
        )

        output_lines.clear()
        is_running = True
        if run_btn_ref.current:
            run_btn_ref.current.disabled = True
        if state.ad_service:
            await state.ad_service.show_interstitial()
        state.is_executing = True
        page.update()

        try:
            output_lines.append(
                f"[*] Creating session{' (' + gpu + ')' if gpu else ' (' + tpu + ')' if tpu else ' (CPU)'}..."
            )
            page.update()

            session_info = await colab_service.new_session(
                name=sess_name,
                gpu=gpu,
                tpu=tpu,
                auth_method=state.auth_method,
            )
            sn = session_info["name"]
            output_lines.append(f"[*] Session '{sn}' created. Running script...")
            page.update()

            # Read and execute the script
            with open(script, "r", encoding="utf-8") as f:
                code = f.read()

            # Inject sys.argv if args provided
            if args:
                argv_setup = f"import sys; sys.argv = {repr([script] + args)}\n"
                code = argv_setup + code

            await colab_service.exec_code(
                code,
                sn,
                timeout=timeout_val,
                auth_method=state.auth_method,
                on_output=lambda t: page.loop.call_soon_threadsafe(_append_output, t),
            )

            output_lines.append("\n[*] Script finished.")

            if not keep:
                output_lines.append(f"[*] Stopping session '{sn}'...")
                page.update()
                await colab_service.stop_session(sn, auth_method=state.auth_method)
                output_lines.append("[*] Session stopped.")
            else:
                output_lines.append(f"[*] Session '{sn}' kept alive.")

            # Refresh sessions
            sessions = await colab_service.list_sessions(auth_method=state.auth_method)
            state.active_sessions = sessions

        except Exception as ex:
            output_lines.append(f"\n[!] Error: {ex}")

        is_running = False
        state.is_executing = False
        if run_btn_ref.current:
            run_btn_ref.current.disabled = False
        page.update()

    def _append_output(text):
        nonlocal _last_output_update
        output_lines.append(text)
        lst = output_list_ref.current
        if lst:
            if (
                lst.controls
                and isinstance(lst.controls[0], ft.Text)
                and lst.controls[0].italic
            ):
                lst.controls.clear()
            from components.ansi_parser import parse_ansi_to_flet_text

            is_error = (
                text.startswith("Error")
                or text.startswith("Traceback")
                or "Error:" in text
            )
            lst.controls.append(
                parse_ansi_to_flet_text(
                    raw_text=text, default_size=tokens.FONT_SM, is_error=is_error
                )
            )
        now = time.monotonic()
        if now - _last_output_update >= 0.1:
            _last_output_update = now
            if lst:
                lst.update()
            else:
                page.update()

    def _on_clear(e):
        output_lines.clear()
        lst = output_list_ref.current
        if lst:
            lst.controls.clear()
            lst.controls.append(
                ft.Text(
                    "Output will appear here...",
                    size=tokens.FONT_SM,
                    color=ft.Colors.with_opacity(0.3, ft.Colors.WHITE),
                    font_family="RobotoMono",
                    italic=True,
                )
            )
        page.update()

    # ── Layout ────────────────────────────────────────────────────────────────
    from components.brand_header import build_brand_header

    view_content = ft.Column(
        controls=[
            build_brand_header(),
            ft.Column(
                controls=[
                    # Script picker
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                section_header("SCRIPT"),
                                glass_card(
                                    ft.Column(
                                        controls=[
                                            ft.TextField(
                                                ref=script_path_ref,
                                                label="Script path",
                                                hint_text="/path/to/script.py",
                                                prefix_icon=ft.Icons.CODE_ROUNDED,
                                                border_radius=tokens.RADIUS_MD,
                                                text_size=tokens.FONT_MD,
                                                expand=True,
                                                read_only=True,
                                            ),
                                            ft.IconButton(
                                                icon=ft.Icons.FOLDER_OPEN_ROUNDED,
                                                on_click=lambda e: page.run_task(
                                                    _on_browse_click, e
                                                ),
                                                tooltip="Browse",
                                            ),
                                        ],
                                        spacing=tokens.SPACE_SM,
                                    )
                                ),
                            ],
                            spacing=0,
                        ),
                        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
                    ),
                    # Hardware
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                section_header("HARDWARE"),
                                glass_card(
                                    ft.Column(
                                        controls=[
                                            ft.SegmentedButton(
                                                allow_multiple_selection=False,
                                                selected=["CPU"],
                                                on_change=_on_hardware_change,
                                                segments=[
                                                    ft.Segment(
                                                        value="CPU",
                                                        label=ft.Text("CPU"),
                                                        icon=ft.Icon(
                                                            ft.Icons.MEMORY_ROUNDED
                                                        ),
                                                    ),
                                                    ft.Segment(
                                                        value="GPU",
                                                        label=ft.Text("GPU"),
                                                        icon=ft.Icon(
                                                            ft.Icons.DEVELOPER_BOARD_ROUNDED
                                                        ),
                                                    ),
                                                    ft.Segment(
                                                        value="TPU",
                                                        label=ft.Text("TPU"),
                                                        icon=ft.Icon(
                                                            ft.Icons.BOLT_ROUNDED
                                                        ),
                                                    ),
                                                ],
                                            ),
                                            tip_text(
                                                "CPU is always free. T4 GPU and TPU are free with limits."
                                            ),
                                            ft.Dropdown(
                                                ref=gpu_ref,
                                                label="GPU Model",
                                                options=[
                                                    ft.dropdown.Option(
                                                        key="T4",
                                                        text="T4  ·  Free tier",
                                                    ),
                                                    ft.dropdown.Option(
                                                        key="L4", text="L4  ·  Pro"
                                                    ),
                                                    ft.dropdown.Option(
                                                        key="G4", text="G4  ·  Pro"
                                                    ),
                                                    ft.dropdown.Option(
                                                        key="A100", text="A100  ·  Pro+"
                                                    ),
                                                    ft.dropdown.Option(
                                                        key="H100", text="H100  ·  Pro+"
                                                    ),
                                                ],
                                                value="T4",
                                                border_radius=tokens.RADIUS_MD,
                                                visible=False,
                                            ),
                                            ft.Dropdown(
                                                ref=tpu_ref,
                                                label="TPU Model",
                                                options=[
                                                    ft.dropdown.Option(
                                                        key="v5e1",
                                                        text="v5e1  ·  Free tier",
                                                    ),
                                                    ft.dropdown.Option(
                                                        key="v6e1",
                                                        text="v6e1  ·  Free tier",
                                                    ),
                                                ],
                                                value="v5e1",
                                                border_radius=tokens.RADIUS_MD,
                                                visible=False,
                                            ),
                                        ],
                                        spacing=tokens.SPACE_MD,
                                    ),
                                ),
                            ],
                            spacing=0,
                        ),
                        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
                    ),
                    # Options
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                section_header("OPTIONS"),
                                glass_card(
                                    ft.Column(
                                        controls=[
                                            ft.TextField(
                                                ref=session_name_ref,
                                                label="Session Name",
                                                hint_text="Auto-generated if blank",
                                                prefix_icon=ft.Icons.LABEL_OUTLINE_ROUNDED,
                                                border_radius=tokens.RADIUS_MD,
                                                text_size=tokens.FONT_MD,
                                            ),
                                            ft.Dropdown(
                                                ref=timeout_ref,
                                                label="Timeout",
                                                options=[
                                                    ft.dropdown.Option(str(t), f"{t}s")
                                                    for t in constants.TIMEOUT_OPTIONS
                                                ],
                                                value=str(state.default_timeout),
                                                border_radius=tokens.RADIUS_MD,
                                            ),
                                            ft.Row(
                                                controls=[
                                                    ft.Switch(
                                                        ref=keep_ref, value=False
                                                    ),
                                                    ft.Column(
                                                        controls=[
                                                            ft.Text(
                                                                "Keep session alive",
                                                                size=tokens.FONT_MD,
                                                                weight=ft.FontWeight.W_500,
                                                            ),
                                                            ft.Text(
                                                                "Session stays running after script finishes",
                                                                size=tokens.FONT_XS,
                                                                color=ft.Colors.ON_SURFACE_VARIANT,
                                                            ),
                                                        ],
                                                        spacing=tokens.SPACE_XXS,
                                                        expand=True,
                                                    ),
                                                ],
                                                spacing=tokens.SPACE_MD,
                                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                            ),
                                        ],
                                        spacing=tokens.SPACE_MD,
                                    ),
                                ),
                            ],
                            spacing=0,
                        ),
                        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
                    ),
                    # Execution
                    ft.Container(height=tokens.SPACE_MD),
                    # Run button
                    ft.Container(
                        content=ft.FilledButton(
                            ref=run_btn_ref,
                            content=ft.Text("Run Script"),
                            icon=ft.Icons.ROCKET_LAUNCH_ROUNDED,
                            on_click=lambda e: page.run_task(_on_run, e),
                            width=float("inf"),
                            style=ft.ButtonStyle(
                                padding=ft.Padding(
                                    tokens.SPACE_XL,
                                    tokens.SPACE_MD,
                                    tokens.SPACE_XL,
                                    tokens.SPACE_MD,
                                ),
                            ),
                        ),
                        padding=ft.Padding(
                            tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, 0
                        ),
                    ),
                    # Output
                    ft.Container(
                        content=build_output_panel(
                            list_ref=output_list_ref,
                            lines=output_lines,
                            is_visible=True,
                            on_clear=_on_clear,
                        ),
                        padding=ft.Padding(
                            tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, 0
                        ),
                    ),
                    ft.Divider(height=tokens.SPACE_SM, color=ft.Colors.TRANSPARENT),
                    build_banner_ad(page),
                    ft.Container(height=tokens.SPACE_XL),
                ],
                spacing=0,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
        ],
        expand=True,
        spacing=0,
    )

    return ft.View(
        route="/run",
        controls=[view_content],
        padding=0,
        appbar=ft.AppBar(
            leading=ft.Container(
                content=ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                    on_click=on_back,
                    icon_size=tokens.ICON_MD,
                    tooltip="Back",
                ),
                padding=ft.Padding(tokens.SPACE_XS, 0, 0, 0),
            ),
            leading_width=48,
            title=ft.Text(
                "Quick Run",
                size=tokens.FONT_LG,
                weight=ft.FontWeight.W_700,
                color=ft.Colors.ON_SURFACE,
            ),
            center_title=True,
            bgcolor=ft.Colors.TRANSPARENT,
            actions=[theme_btn] if theme_btn else [],
        ),
    )
