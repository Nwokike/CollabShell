import flet as ft

from core import tokens


class FilesController:
    def __init__(
        self,
        page: ft.Page,
        colab_service,
        state,
        session_name: str,
        on_back,
        snack,
        theme_btn,
    ):
        self.page = page
        self.colab_service = colab_service
        self.state = state
        self.session_name = session_name
        self.on_back = on_back
        self.snack = snack
        self.theme_btn = theme_btn

        self.current_path = state.current_path or "/content"
        self.files = []
        self.is_loading = False
        self.selected_files = set()

        self.file_list_container = ft.Container(
            padding=ft.Padding(tokens.SPACE_SM, 0, tokens.SPACE_SM, 0),
            expand=True,
        )
        self.breadcrumb_container = ft.Container(
            expand=True,
        )
        self.action_bar_container = ft.Container()

        self.upload_fab = ft.FloatingActionButton(
            "Upload",
            icon=ft.Icons.UPLOAD_FILE_ROUNDED,
            on_click=lambda e: self.page.run_task(self.on_upload_click, e),
        )

    async def load_files(self, path=None):
        from views.files.explorer import load_files_impl

        await load_files_impl(self, path)

    def on_file_tap(self, file_info):
        from views.files.explorer import on_file_tap_impl

        on_file_tap_impl(self, file_info)

    async def on_upload_click(self, e=None):
        from views.files.actions import on_upload_click_impl

        await on_upload_click_impl(self, e)

    def build_action_bar(self):
        from views.files.components import build_action_bar_impl

        return build_action_bar_impl(self)

    def build_file_list(self):
        from views.files.explorer import build_file_list_impl

        return build_file_list_impl(self)

    def build_breadcrumb(self):
        from views.files.explorer import build_breadcrumb_impl

        return build_breadcrumb_impl(self)

    def on_navigate_up(self, e):
        import posixpath

        if self.current_path and self.current_path != "/":
            parent = posixpath.dirname(posixpath.normpath(self.current_path))
            if not parent or parent == ".":
                parent = "/"
            self.page.run_task(self.load_files, parent)
