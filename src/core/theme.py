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
    LIGHT_TEXT_DIM = "#64748B"
    LIGHT_HIGHLIGHT = "#F9AB00"  # Colab amber (brand primary)
    LIGHT_PRIMARY_VARIANT = "#E09600"  # Darker amber
    LIGHT_PRIMARY = "#F9AB00"  # Colab amber

    # ─── DARK PALETTE ─────────────────────────────────────────────────────────
    DARK_BG = "#1E1E2E"  # Deep charcoal
    DARK_SURFACE = "#16161F"  # Deeper card background
    DARK_TEXT = "#F8F8F2"  # Chalk white
    DARK_PRIMARY = "#FFB74D"  # Warm amber (lighter for dark bg)
    DARK_PRIMARY_VARIANT = "#FFA726"  # Slightly deeper amber
    DARK_TEXT_DIM = "#8B8FA3"  # Muted gray
    DARK_HIGHLIGHT = "#FFB74D"  # Warm amber

    # ─── Semantic colors ──────────────────────────────────────────────────────
    SUCCESS = "#4CAF50"  # Green — session running, auth OK
    WARNING = "#FF9800"  # Orange — caution, limits
    ERROR = "#EF5350"  # Red — errors, stopped
    INFO = "#42A5F5"  # Blue — TPU badge, info
    DIVIDER = "#E2E8F0"
    DARK_DIVIDER = "#2D2D3F"

    # ─── Hardware badge colors ────────────────────────────────────────────────
    BADGE_CPU = "#78909C"  # Blue-gray for CPU
    BADGE_GPU = "#FFB74D"  # Amber for GPU
    BADGE_TPU = "#42A5F5"  # Blue for TPU
    BADGE_FREE = "#4CAF50"  # Green — free tier
    BADGE_PAID = "#AB47BC"  # Purple — paid tier

    # ─── Terminal colors ──────────────────────────────────────────────────────
    TERMINAL_BG = "#0D0D1A"
    TERMINAL_HEADER = "#1A1A2E"
    TERMINAL_CURSOR = "#28C840"
    TERMINAL_DOT_RED = "#FF5F57"
    TERMINAL_DOT_YELLOW = "#FEBC2E"
    TERMINAL_DOT_GREEN = "#28C840"


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
        )
