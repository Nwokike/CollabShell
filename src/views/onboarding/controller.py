import flet as ft

from core import constants
from views.onboarding.slides import build_page_1, build_page_2, build_page_3


def make_slide_controller(
    page: ft.Page,
    state,
    storage,
    on_complete,
    current_page,
    slide_container,
    indicator_row,
    back_btn,
    next_btn,
    sign_in_btn,
    auth_url_text,
    auth_code_field,
    verify_btn,
    auth_status_text,
    start_auth_task,
    submit_code_task,
):
    def build_slide(index):
        if index == 0:
            return build_page_1()
        elif index == 1:
            return build_page_2()
        else:
            return build_page_3(
                sign_in_btn,
                auth_url_text,
                auth_code_field,
                verify_btn,
                auth_status_text,
                start_auth_task,
                submit_code_task,
            )

    def build_indicators():
        dots = []
        for i in range(3):
            dots.append(
                ft.Container(
                    width=10 if i == current_page["index"] else 6,
                    height=6,
                    border_radius=3,
                    bgcolor=ft.Colors.PRIMARY
                    if i == current_page["index"]
                    else ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE),
                )
            )
        return dots

    async def _on_get_started(e):
        state.onboarding_done = True
        await storage.set(constants.STORAGE_ONBOARDING_DONE, "true")
        if on_complete:
            on_complete()

    def update_view():
        idx = current_page["index"]
        if slide_container.current:
            slide_container.current.content = build_slide(idx)
        if indicator_row.current:
            indicator_row.current.controls = build_indicators()
        if back_btn.current:
            back_btn.current.visible = idx > 0
        if next_btn.current:
            if idx == 2:
                next_btn.current.content = ft.Text("Get Started")
                next_btn.current.on_click = lambda e: page.run_task(_on_get_started, e)
                next_btn.current.disabled = not state.is_authenticated
            else:
                next_btn.current.content = ft.Text("Next")
                next_btn.current.on_click = on_next
                next_btn.current.disabled = False
        page.update()

    def on_next(e=None):
        if current_page["index"] < 2:
            current_page["index"] += 1
            update_view()

    def on_back(e=None):
        if current_page["index"] > 0:
            current_page["index"] -= 1
            update_view()

    def on_swipe(e: ft.DragEndEvent):
        if e.primary_velocity is not None:
            if e.primary_velocity < -200:  # Swipe left → next
                on_next(e)
            elif e.primary_velocity > 200:  # Swipe right → back
                on_back(e)

    return build_slide, build_indicators, update_view, on_next, on_back, on_swipe
