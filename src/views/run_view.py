"""Quick Run view — one-shot script execution (colab run equivalent)."""

from __future__ import annotations

import flet as ft

from core import tokens, constants
from core.styles import section_header, tip_text, build_banner_ad
from components.output_panel import build_output_panel


def build_run_view(
    page: ft.Page,
    colab_service,
    state,
    on_back=None,
    snack=None,
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
    is_running = False

    file_picker = ft.FilePicker()
    page.overlay.append(file_picker)

    def _on_file_picked(e: ft.FilePickerResultEvent):
        if e.files and script_path_ref.current:
            script_path_ref.current.value = e.files[0].path
            page.update()

    file_picker.on_result = _on_file_picked

    hardware_type = "CPU"

    def _on_hardware_change(e):
        nonlocal hardware_type
        selected = e.control.selected
        if selected:
            hardware_type = list(selected)[0]
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
            with open(script, "r") as f:
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
                on_output=lambda t: _append_output(t),
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
        page.update()

    def _append_output(text):
        output_lines.append(text)
        page.update()

    def _on_clear(e):
        output_lines.clear()
        page.update()

    # ── Layout ────────────────────────────────────────────────────────────────
    from core.styles import standard_brand_appbar

    app_bar = standard_brand_appbar(
        title_text="Quick Run",
        on_back=on_back,
    )

    view_content = ft.Column(
        controls=[
            app_bar,
            ft.Column(
                controls=[
                    # Script picker
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                section_header("SCRIPT"),
                                ft.Container(
                                    content=ft.Row(
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
                                                on_click=lambda e: (
                                                    file_picker.pick_files(
                                                        allowed_extensions=["py"],
                                                        dialog_title="Select Python Script",
                                                    )
                                                ),
                                                tooltip="Browse",
                                            ),
                                        ],
                                        spacing=tokens.SPACE_SM,
                                    ),
                                    padding=ft.Padding(
                                        tokens.SPACE_LG, 0, tokens.SPACE_LG, 0
                                    ),
                                ),
                                ft.Container(
                                    content=ft.TextField(
                                        ref=args_ref,
                                        label="Script arguments",
                                        hint_text="--arg1 value1 --arg2 value2",
                                        prefix_icon=ft.Icons.SETTINGS_ROUNDED,
                                        border_radius=tokens.RADIUS_MD,
                                        text_size=tokens.FONT_MD,
                                    ),
                                    padding=ft.Padding(
                                        tokens.SPACE_LG,
                                        tokens.SPACE_SM,
                                        tokens.SPACE_LG,
                                        0,
                                    ),
                                ),
                            ],
                            spacing=0,
                        ),
                    ),
                    # Hardware
                    section_header("HARDWARE"),
                    ft.Container(
                        content=ft.SegmentedButton(
                            selected={"CPU"},
                            on_change=_on_hardware_change,
                            segments=[
                                ft.Segment(
                                    value="CPU",
                                    label=ft.Text("CPU"),
                                    icon=ft.Icon(ft.Icons.MEMORY_ROUNDED),
                                ),
                                ft.Segment(
                                    value="GPU",
                                    label=ft.Text("GPU"),
                                    icon=ft.Icon(ft.Icons.DEVELOPER_BOARD_ROUNDED),
                                ),
                                ft.Segment(
                                    value="TPU",
                                    label=ft.Text("TPU"),
                                    icon=ft.Icon(ft.Icons.BOLT_ROUNDED),
                                ),
                            ],
                        ),
                        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
                    ),
                    ft.Container(
                        content=tip_text(
                            "CPU is always free. T4 GPU and TPU are free with limits."
                        ),
                        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
                    ),
                    ft.Container(
                        content=ft.Dropdown(
                            ref=gpu_ref,
                            label="GPU Model",
                            options=[
                                ft.dropdown.Option(key="T4", text="T4  ·  Free tier"),
                                ft.dropdown.Option(key="L4", text="L4  ·  Pro"),
                                ft.dropdown.Option(key="A100", text="A100  ·  Pro+"),
                                ft.dropdown.Option(key="H100", text="H100  ·  Pro+"),
                            ],
                            value="T4",
                            border_radius=tokens.RADIUS_MD,
                        ),
                        padding=ft.Padding(
                            tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, 0
                        ),
                    ),
                    ft.Container(
                        content=ft.Dropdown(
                            ref=tpu_ref,
                            label="TPU Model",
                            options=[
                                ft.dropdown.Option(
                                    key="v5e1", text="v5e1  ·  Free tier"
                                ),
                                ft.dropdown.Option(
                                    key="v6e1", text="v6e1  ·  Free tier"
                                ),
                            ],
                            value="v5e1",
                            border_radius=tokens.RADIUS_MD,
                        ),
                        padding=ft.Padding(
                            tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, 0
                        ),
                    ),
                    # Options
                    section_header("OPTIONS"),
                    ft.Container(
                        content=ft.Column(
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
                                        ft.Switch(ref=keep_ref, value=False),
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
                        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
                    ),
                    # Run button
                    ft.Container(
                        content=ft.FilledButton(
                            content=ft.Text(
                                "Run Script" if not is_running else "Running..."
                            ),
                            icon=ft.Icons.ROCKET_LAUNCH_ROUNDED,
                            on_click=lambda e: page.run_task(_on_run, e),
                            disabled=is_running,
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
    )
