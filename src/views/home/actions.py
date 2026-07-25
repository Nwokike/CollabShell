import flet as ft

from core import tokens


def action_button(icon, label, on_click, color=None):
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(
                    content=ft.Icon(
                        icon, size=tokens.ICON_XL, color=color or ft.Colors.PRIMARY
                    ),
                    width=tokens.CARD_ICON_CONTAINER,
                    height=tokens.CARD_ICON_CONTAINER,
                    border_radius=tokens.RADIUS_MD,
                    bgcolor=ft.Colors.with_opacity(0.1, color or ft.Colors.PRIMARY),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Text(
                    label,
                    size=tokens.FONT_XS,
                    text_align=ft.TextAlign.CENTER,
                    weight=ft.FontWeight.W_500,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_SM,
        ),
        on_click=on_click,
        expand=True,
        ink=True,
        padding=ft.Padding(
            tokens.SPACE_SM, tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_MD
        ),
        border_radius=tokens.RADIUS_MD,
    )


def show_session_selector(
    page: ft.Page, colab_service, state, mode: str, on_new_session, navigate
):
    def _on_new(e):
        dialog.content = ft.Container(
            width=300,
            padding=ft.Padding(
                tokens.SPACE_XL, tokens.SPACE_XL, tokens.SPACE_XL, tokens.SPACE_XL
            ),
            content=ft.Column(
                controls=[
                    ft.ProgressRing(stroke_width=2),
                    ft.Container(height=16),
                    ft.Text(
                        "Preparing...",
                        size=tokens.FONT_MD,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                tight=True,
            ),
        )
        page.update()

        async def _do_new():
            import asyncio

            await asyncio.sleep(0.2)
            dialog.open = False
            page.update()
            if on_new_session:
                on_new_session(mode)

        page.run_task(_do_new)

    def make_on_select(session_name):
        def handler(e):
            dialog.content = ft.Container(
                width=300,
                padding=ft.Padding(
                    tokens.SPACE_XL,
                    tokens.SPACE_XL,
                    tokens.SPACE_XL,
                    tokens.SPACE_XL,
                ),
                content=ft.Column(
                    controls=[
                        ft.ProgressRing(stroke_width=2),
                        ft.Container(height=16),
                        ft.Text(
                            f"Opening {session_name}...",
                            size=tokens.FONT_MD,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                    tight=True,
                ),
            )
            page.update()

            async def _do_navigate():
                import asyncio
                import urllib.parse

                await asyncio.sleep(0.2)
                dialog.open = False
                page.update()
                if navigate:
                    encoded_session = urllib.parse.quote(session_name)
                    if mode == "notebook":
                        await navigate(f"/session?session={encoded_session}")
                    elif mode == "terminal":
                        await navigate(
                            f"/session?session={encoded_session}&tab=terminal"
                        )
                    elif mode == "files":
                        await navigate(f"/files?session={encoded_session}")

            page.run_task(_do_navigate)

        return handler

    controls = [
        ft.ListTile(
            leading=ft.Icon(ft.Icons.ADD_ROUNDED, color=ft.Colors.PRIMARY),
            title=ft.Text(
                "New Session", color=ft.Colors.PRIMARY, weight=ft.FontWeight.BOLD
            ),
            on_click=_on_new,
        ),
        ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT),
    ]

    if not state.active_sessions:
        controls.append(
            ft.ListTile(
                title=ft.Text(
                    "No active sessions available.",
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                disabled=True,
            )
        )
    else:
        for s in state.active_sessions:
            name = s.get("name", "Unknown")
            status = s.get("status", "IDLE")
            accel = s.get("accelerator_label", "CPU")
            controls.append(
                ft.ListTile(
                    leading=ft.Icon(
                        ft.Icons.STORAGE_ROUNDED, color=ft.Colors.ON_SURFACE
                    ),
                    title=ft.Text(name, weight=ft.FontWeight.W_500),
                    subtitle=ft.Text(f"{status} • {accel}", size=tokens.FONT_XS),
                    on_click=make_on_select(name),
                )
            )

    dialog = ft.AlertDialog(
        content=ft.Container(
            width=400,
            padding=ft.Padding(
                tokens.SPACE_SM, tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_SM
            ),
            content=ft.Column(
                controls=[
                    ft.Text(
                        "Select Session"
                        if mode == "notebook"
                        else f"Select Session for {mode.capitalize()}",
                        size=tokens.FONT_LG,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Divider(height=1, color=ft.Colors.TRANSPARENT),
                    ft.Column(
                        controls=controls, spacing=0, scroll=ft.ScrollMode.ADAPTIVE
                    ),
                ],
                tight=True,
                spacing=tokens.SPACE_SM,
            ),
        ),
        shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_LG),
    )
    page.show_dialog(dialog)
