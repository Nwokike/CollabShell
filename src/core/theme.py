"""Design system — Colab-branded themes inspired by Google Colab's amber palette."""

import flet as ft


class AppColors:
    # ─── COLAB BRAND PALETTE ──────────────────────────────────────────────────
    # Google Colab primary: warm amber/orange #F9AB00
    # Adapted into a premium two-tone palette for light & dark modes.

    # ─── LIGHT PALETTE ────────────────────────────────────────────────────────
    LIGHT_BG = "#FFFFFF"
    LIGHT_SURFACE = "#F3F4F6"
    LIGHT_TEXT = "#1E293B"
    LIGHT_TEXT_DIM = "#475569"
    LIGHT_HIGHLIGHT = "#D87607"  # Brand orange from icon
    LIGHT_PRIMARY_VARIANT = "#BA6200"  # Darker orange
    LIGHT_PRIMARY = "#D87607"  # Brand orange from icon

    # ─── DARK PALETTE ─────────────────────────────────────────────────────────
    DARK_BG = "#1E1E2E"  # Deep charcoal
    DARK_SURFACE = "#16161F"  # Deeper card background
    DARK_TEXT = "#F8F8F2"  # Chalk white
    DARK_PRIMARY = "#E58514"  # Warm orange (lighter for dark bg)
    DARK_PRIMARY_VARIANT = "#D87607"  # Slightly deeper orange
    DARK_TEXT_DIM = "#8B8FA3"  # Muted gray
    DARK_HIGHLIGHT = "#E58514"  # Warm orange

    # ─── Semantic colors ──────────────────────────────────────────────────────
    SUCCESS = "#4CAF50"  # Green — session running, auth OK
    WARNING = "#FF9800"  # Orange — caution, limits
    ERROR = "#EF5350"  # Red — errors, stopped
    INFO = "#42A5F5"  # Blue — TPU badge, info
    DIVIDER = "#E2E8F0"
    DARK_DIVIDER = "#2D2D3F"

    # ─── Hardware badge colors ────────────────────────────────────────────────
    BADGE_CPU = "#78909C"  # Blue-gray for CPU
    BADGE_GPU = "#E58514"  # Orange for GPU
    BADGE_TPU = "#42A5F5"  # Blue for TPU
    BADGE_FREE = "#4CAF50"  # Green — free tier
    BADGE_PAID = "#AB47BC"  # Purple — paid tier

    # ─── Terminal colors ──────────────────────────────────────────────────────
    TERMINAL_BG = "#0D0D1A"
    LOG_TERMINAL_BG = "#0D0D0D"
    TERMINAL_GREEN = "#A6E22E"
    TERMINAL_HEADER = "#1A1A2E"
    TERMINAL_CURSOR = "#28C840"
    TERMINAL_DOT_RED = "#FF5F57"
    TERMINAL_DOT_YELLOW = "#FEBC2E"
    TERMINAL_DOT_GREEN = "#28C840"

    # ─── Adaptive glass (elevation) surfaces ──────────────────────────────────
    # Explicit per-mode values so cards never rely on M3 tokens the custom
    # Colab ColorScheme doesn't set (surface_container_low would fall back to
    # the Material default and wash out). These replace the old
    # with_opacity(0.05, ON_SURFACE) pattern that read as near-invisible in
    # light mode.
    LIGHT_GLASS_BG = "#F1F5F9"  # soft slate-100 card on white
    LIGHT_GLASS_BORDER = "#E2E8F0"  # slate-200 hairline
    DARK_GLASS_BG = "#26263A"  # raised card on #1E1E2E
    DARK_GLASS_BORDER = "#2D2D3F"  # dark hairline


def _resolve_page(page: "ft.Page | None") -> "ft.Page | None":
    """Return the given page, else the running app's page (None if unavailable)."""
    if page is not None:
        return page
    try:
        return ft.context.page
    except RuntimeError:
        return None


def is_light_theme(page: "ft.Page | None" = None) -> bool:
    """Resolve the *effective* light/dark mode, handling SYSTEM via platform brightness.

    ``page.theme_mode`` only holds the *requested* mode — in ``SYSTEM`` mode it
    stays ``SYSTEM`` and the client resolves light/dark from the host OS. We
    mirror that resolution with the read-only ``page.platform_brightness`` so
    adaptive helpers work in all three modes. Pass ``ft.context.page`` (or leave
    it unset to auto-resolve); defaults to light when the brightness is unknown.

    Reading the observable ``state.theme_mode`` / ``state.theme_revision`` here
    means any component whose render calls this will re-render when the theme
    mode toggles or the platform brightness flips.
    """
    # Read observables so callers subscribe (kept separate from the page read).
    from src.core.state import state as _state

    requested = _state.theme_mode
    revision = _state.theme_revision  # noqa: F841  (subscribe for re-render)

    p = _resolve_page(page)
    if p is None:
        return True
    tm = getattr(p, "theme_mode", None) or requested
    if tm == ft.ThemeMode.LIGHT:
        return True
    if tm == ft.ThemeMode.DARK:
        return False
    # SYSTEM (or unset): follow the host platform brightness.
    brightness = getattr(p, "platform_brightness", None)
    if brightness == ft.Brightness.DARK:
        return False
    if brightness == ft.Brightness.LIGHT:
        return True
    return True  # brightness not yet reported — Colab's default surface is light


def adaptive_glass_bg(page: "ft.Page | None" = None):
    """Return the card background color for the active theme mode."""
    return AppColors.LIGHT_GLASS_BG if is_light_theme(page) else AppColors.DARK_GLASS_BG


def adaptive_glass_border(page: "ft.Page | None" = None):
    """Return the card hairline border color for the active theme mode."""
    return (
        AppColors.LIGHT_GLASS_BORDER
        if is_light_theme(page)
        else AppColors.DARK_GLASS_BORDER
    )


class AppTheme:
    @staticmethod
    def get_dark_theme() -> ft.Theme:
        return ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=AppColors.DARK_PRIMARY,
                primary_container=AppColors.DARK_PRIMARY_VARIANT,
                secondary=AppColors.DARK_PRIMARY_VARIANT,
                secondary_container=AppColors.DARK_PRIMARY_VARIANT,
                tertiary=AppColors.DARK_PRIMARY,
                tertiary_container=AppColors.DARK_PRIMARY_VARIANT,
                surface=AppColors.DARK_BG,
                on_surface=AppColors.DARK_TEXT,
                on_surface_variant=AppColors.DARK_TEXT_DIM,
                error=AppColors.ERROR,
                on_primary=AppColors.DARK_BG,
                on_secondary=AppColors.DARK_BG,
                on_tertiary=AppColors.DARK_BG,
                surface_container_highest=AppColors.DARK_SURFACE,
                outline=AppColors.DARK_DIVIDER,
            ),
            font_family="Outfit",
        )

    @staticmethod
    def get_light_theme() -> ft.Theme:
        return ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=AppColors.LIGHT_PRIMARY,
                primary_container=AppColors.LIGHT_PRIMARY_VARIANT,
                secondary=AppColors.LIGHT_PRIMARY_VARIANT,
                secondary_container=AppColors.LIGHT_PRIMARY_VARIANT,
                tertiary=AppColors.LIGHT_PRIMARY,
                tertiary_container=AppColors.LIGHT_PRIMARY_VARIANT,
                surface=AppColors.LIGHT_BG,
                on_surface=AppColors.LIGHT_TEXT,
                on_surface_variant=AppColors.LIGHT_TEXT_DIM,
                error=AppColors.ERROR,
                on_primary=AppColors.LIGHT_BG,
                on_secondary=AppColors.LIGHT_BG,
                on_tertiary=AppColors.LIGHT_BG,
                surface_container_highest=AppColors.LIGHT_SURFACE,
                outline=AppColors.DIVIDER,
            ),
            font_family="Outfit",
        )
