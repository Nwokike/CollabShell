import flet as ft
from core import constants
from core.theme import AppColors


def make_auth_handlers(
    page: ft.Page,
    colab_service,
    state,
    sign_in_btn,
    auth_url_text,
    auth_code_field,
    verify_btn,
    auth_status_text,
    next_btn,
):
    async def start_auth(e=None):
        try:
            if sign_in_btn.current:
                sign_in_btn.current.disabled = True
                sign_in_btn.current.content = ft.Text("Generating link...")
            page.update()

            url = await colab_service.get_auth_url()
            await ft.UrlLauncher().launch_url(url)

            if auth_url_text.current:
                auth_url_text.current.value = "Paste the authorization code below."
                auth_url_text.current.visible = True
            if auth_code_field.current:
                auth_code_field.current.visible = True
            if verify_btn.current:
                verify_btn.current.visible = True

            if sign_in_btn.current:
                sign_in_btn.current.content = ft.Text("Link opened in browser")
            page.update()
        except Exception as ex:
            if sign_in_btn.current:
                sign_in_btn.current.disabled = False
                sign_in_btn.current.content = ft.Text(constants.LBL_SIGN_IN)
            if auth_status_text.current:
                auth_status_text.current.value = f"Error: {ex}"
                auth_status_text.current.color = AppColors.ERROR
                auth_status_text.current.visible = True
            page.update()

    async def submit_code(e=None):
        code = auth_code_field.current.value.strip() if auth_code_field.current else ""
        if not code:
            return

        if auth_status_text.current:
            auth_status_text.current.value = "Verifying..."
            auth_status_text.current.color = ft.Colors.ON_SURFACE_VARIANT
            auth_status_text.current.visible = True
        page.update()

        result = await colab_service.authenticate_oauth2(code)
        if result["success"]:
            state.is_authenticated = True
            state.auth_email = result["email"]
            if auth_status_text.current:
                auth_status_text.current.value = f"✅ Signed in as {result['email']}"
                auth_status_text.current.color = AppColors.SUCCESS
                auth_status_text.current.visible = True
            if next_btn.current:
                next_btn.current.disabled = False
        else:
            if auth_status_text.current:
                auth_status_text.current.value = f"❌ {result['error']}"
                auth_status_text.current.color = AppColors.ERROR
                auth_status_text.current.visible = True
        page.update()

    return start_auth, submit_code
