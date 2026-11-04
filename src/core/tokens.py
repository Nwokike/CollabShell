"""Design tokens — unified spacing, typography, radii, icons, and layout dimensions."""

import flet as ft

# ── Identity icons ────────────────────────────────────────────────────────────
# The assistant's identity glyph. One constant, read by every surface that
# means "this is the assistant": the main FAB, the chat screen's own title and
# empty state, the credit pill, the palette entry, the session FAB menu, the
# in-cell AI button, and the file/terminal explain buttons. They had drifted
# apart (an outline bubble on the chat screen, a sparkle everywhere else), so
# the FAB and the thing the FAB opens looked like two different products.
ASSISTANT_ICON = ft.Icons.CHAT_BUBBLE_ROUNDED

# ── Spacing ───────────────────────────────────────────────────────────────────
SPACE_NONE = 0
SPACE_MICRO = 1
SPACE_NANO = 2
SPACE_XXS = 2
SPACE_XS = 4
SPACE_SM = 6
SPACE_MD = 10
SPACE_LG = 14
SPACE_XL = 16
SPACE_XXL = 22
SPACE_XXXL = 32

# ── Typography ────────────────────────────────────────────────────────────────
FONT_XXS = 8
FONT_XS = 9
FONT_SM = 10
FONT_MD = 12
FONT_LG = 14
FONT_XL = 18
FONT_XXL = 22
FONT_HERO = 30

# ── Corner Radii ──────────────────────────────────────────────────────────────
RADIUS_XS = 4
RADIUS_SM = 8
RADIUS_MD = 12
RADIUS_LG = 16
RADIUS_XL = 24
RADIUS_PILL = 999

# ── Icon Sizes ────────────────────────────────────────────────────────────────
ICON_MICRO = 12
ICON_XS = 14
ICON_SM = 16
ICON_MD = 20
ICON_LG = 24
ICON_XL = 32
ICON_XXL = 48
ICON_XXXL = 80
HERO_ICON_SIZE = 72

# ── Component Layout Dimensions ───────────────────────────────────────────────
INPUT_WIDTH_SM = 100
INPUT_WIDTH_MD = 110
INPUT_WIDTH_LG = 130
CARD_ICON_CONTAINER = 56
ICON_CONTAINER_SM = 44
STEP_BADGE_SIZE = 28
STEP_BADGE_RADIUS = 14

DIALOG_WIDTH = 300
DIALOG_WIDTH_LG = 400
DIALOG_HEIGHT_LG = 480

SPINNER_SM = 20
SPINNER_MD = 24
SPINNER_LG = 28
SPINNER_XL = 32

HEIGHT_SEPARATOR = 16
DIVIDER_THICKNESS = 1

WINDOW_MIN_WIDTH = 360
WINDOW_MIN_HEIGHT = 600

BANNER_WIDTH = 320
BANNER_HEIGHT = 50

# ── Opacity Tokens ────────────────────────────────────────────────────────────
OPACITY_SUBTLE = 0.02
OPACITY_CONTAINER = 0.05
OPACITY_ACCENT = 0.1
OPACITY_CARD = 0.12
