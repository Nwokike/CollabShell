"""Application-wide constants."""

APP_NAME = "Colab Shell"
APP_FULL_NAME = "Colab Shell: Notebook & TTY"
APP_VERSION = "2.1.3"
APP_BUILD_NUMBER = 13
UPDATE_CONFIG_URL = (
    "https://raw.githubusercontent.com/Nwokike/CollabShell/main/version.json"
)
GITHUB_RELEASES_URL = "https://github.com/Nwokike/CollabShell/releases/latest"
PLAY_STORE_URL = "https://play.google.com/store/apps/details?id=ng.kiri.collabshell"
PRIVACY_POLICY_URL = "https://kiri.ng/privacy"
TERMS_OF_SERVICE_URL = "https://kiri.ng/terms"

# ── Storage keys ──────────────────────────────────────────────────────────────
STORAGE_THEME = "colab_theme"
STORAGE_ONBOARDING_DONE = "colab_onboarding_done"
# NOTE: STORAGE_AUTH_METHOD ("colab_auth_method") was retired — the oauth2/adc
# dropdown was removed because flipping to ADC on a machine without
# Application Default Credentials bricked every backend call. Signed-in means
# OAuth2, always. The stored pref is left on-device (never deleted per
# policy) but no longer read; state.auth_method defaults to "oauth2".
STORAGE_DEFAULT_GPU = "colab_default_gpu"
STORAGE_DEFAULT_TPU = "colab_default_tpu"
STORAGE_DEFAULT_HIGH_MEM = "colab_default_high_mem"
STORAGE_DEFAULT_TIMEOUT = "colab_default_timeout"
STORAGE_DEFAULT_ENV = "colab_default_env"
# NOTE: STORAGE_KEEP_ALIVE ("colab_keep_alive") was retired in Phase 5 — the
# Active keep-alive toggle gated nothing after the ping loop was deleted in
# Phase 1. The stored pref is left on-device (never deleted per policy) but no
# longer read. STORAGE_KEEP_ALIVE_ON_DISCONNECT stays live (exit cleanup gate).
STORAGE_KEEP_ALIVE_ON_DISCONNECT = "colab_keep_alive_on_disconnect"
STORAGE_LOG_FORMAT = "colab_log_format"
STORAGE_DRIVE_MOUNT_PATH = "colab_drive_mount_path"
STORAGE_LOGTOSTDERR = "colab_logtostderr"
# Usage cache (account data, NOT local prefs): survives Clear Local Data by
# design — data_section.py deliberately omits these keys. TTL enforced in
# code (usage_cache.CACHE_TTL_SEC). Retired-key policy: removal means stop
# reading, never delete() on-device keys.
STORAGE_USAGE_CACHE = "colab_usage_cache"
STORAGE_USAGE_UPDATED_AT = "colab_usage_updated_at"

# ── Assistant (AI) settings ─────────────────────────────────────────────────
# Local prefs (survive Clear Local Data like the rest of this block). The
# router base URL points at an OpenAI-compatible endpoint; the bundled SKILL.md
# is injected into the system prompt when router_help is on.
STORAGE_AI_MODE = "colab_ai_mode"
STORAGE_AI_MODEL = "colab_ai_model"
STORAGE_AI_ROUTER_URL = "colab_ai_router_url"
STORAGE_AI_HELP = "colab_ai_help"
AI_DEFAULT_ROUTER_URL = "http://127.0.0.1:8082/v1"
TIP_AI_MODE = (
    "Show the Assistant tab and the in-cell AI actions. "
    "Manual work stays exactly the same."
)
# One assistant step = one model call (a streamed reply, or one tool round).
# The Settings "what credits are for" copy is generated from these, never
# hand-typed, so it cannot drift from what is charged.
COST_STEP = 1
DAILY_FREE_CREDITS = 50
DAILY_PREMIUM_CREDITS = 500

# ── Kiri License (license.kiri.ng) ──────────────────────────────────────────
# The only checkout in this build: direct APK installs, Windows and Linux.
# The Worker owns payment policy; we hold a recovery ID and a signed
# entitlement token. A Play AAB is the "play" channel (free + ads, no premium)
# — see core/channel.py.
KIRI_LICENSE_BASE_URL = "https://license.kiri.ng"
# Matches LICENSE_PUBLIC_KEY in kiri-license/wrangler.toml. Public by design —
# it verifies tokens offline and can never sign anything.
KIRI_LICENSE_PUBLIC_KEY = (
    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE-YfZ-yKdG3wYF1IR0XcpJH4RclAB"
    "nddMmAGXFI2J8sbC4gWY2POKc8hVrn0_uHxDZ9ufzwzg4buUimW-IEw4Uw"
)
# Stable app identifier sent to the Worker. The same value is used for
# checkout, restore and status — a temporary install id would orphan
# purchases on reinstall.
KIRI_LICENSE_APP_ID = "ng.kiri.collabshell"
KIRI_LICENSE_TIMEOUT = 15.0
SETTING_RECOVERY_ID = "kiri_recovery_id"
SETTING_TOKEN = "kiri_token"
SETTING_PRODUCT = "kiri_product"

# ── Hardware options (from colab_cli.client.Accelerator) ──────────────────────
# Free tier: CPU (always), T4 GPU (limited), TPU v5e1/v6e1 (limited)
# Paid: L4, G4, A100, H100
GPU_OPTIONS = ["T4", "L4", "G4", "A100", "H100"]
TPU_OPTIONS = ["v5e1", "v6e1"]
HARDWARE_TYPES = ["CPU", "GPU", "TPU"]

# Free-tier indicators — show contextual tips to users
FREE_TIER_GPU = ["T4"]
FREE_TIER_TPU = ["v5e1", "v6e1"]
PAID_TIER_GPU = ["L4", "G4", "A100", "H100"]
# Accelerators offering a single machine shape: High-RAM is ignored for these
# (matches upstream colab_cli.client.HIGH_MEM_ONLY_ACCELERATORS).
SINGLE_SHAPE_ACCELERATORS = ["L4", "V5E1", "V6E1"]

# ── Timeout presets ───────────────────────────────────────────────────────────
TIMEOUT_OPTIONS = [10, 30, 60, 120, 300, 600]
DEFAULT_TIMEOUT = 30

# ── Log export formats (from colab_cli.converter) ─────────────────────────────
LOG_FORMATS = ["ipynb", "md", "jsonl", "txt"]

# ── Auth methods (from colab_cli.auth.AuthProvider) ───────────────────────────
AUTH_METHODS = ["oauth2", "adc"]

# ── Labels ────────────────────────────────────────────────────────────────────
LBL_HOME = "Home"
LBL_HISTORY = "History"
LBL_SETTINGS = "Settings"
LBL_NOTEBOOKS = "Notebooks"
LBL_TERMINAL = "Terminal"
LBL_NEW_SESSION = "New Session"
LBL_NEW_NOTEBOOK = "New Notebook"
LBL_NEW_TERMINAL = "New Terminal"
LBL_QUICK_RUN = "Quick Run"
LBL_FILES = "Files"
LBL_CLOUD_FILES = "Cloud Files"
LBL_SESSIONS = "Sessions"
LBL_ACTIVE_SESSIONS = "Active Sessions"
LBL_EXECUTE = "Execute"
LBL_STOP = "Stop"
LBL_RESTART = "Restart Kernel"
LBL_UPLOAD = "Upload"
LBL_DOWNLOAD = "Download"
LBL_INSTALL = "Install Packages"
LBL_MOUNT_DRIVE = "Mount Drive"
LBL_AUTH_GCP = "Auth GCP"
LBL_OPEN_BROWSER = "Colab Web"
LBL_EXPORT_LOG = "Export Log"
LBL_MANAGE_COMPUTE = "Manage Compute"
LBL_SIGN_IN = "Sign in to Google"
LBL_RE_AUTH = "Re-authenticate"

# ── Error messages ────────────────────────────────────────────────────────────
ERR_NETWORK = "Network error. Check your connection."
ERR_GENERIC = "Something went wrong. Please try again."
ERR_NO_SESSION = "No active sessions. Create one first."
ERR_SESSION_LOST = "Session appears to be lost. It may have timed out."
ERR_AUTH_EXPIRED = "Authentication expired. Please sign in again."
ERR_CLI_NOT_FOUND = "Google Colab CLI is not installed or not accessible."

# ── Help / tips (contextual guidance for non-developers) ──────────────────────
TIP_CPU = "CPU sessions are always free and available. Great for light work."
TIP_GPU_FREE = "T4 GPU is available on the free tier with usage limits."
TIP_GPU_PAID = "This GPU requires Colab Pro or Pay As You Go."
TIP_TPU_FREE = "TPU is available on the free tier with usage limits."
TIP_SESSION_NAME = "Optional — a random name will be generated if left blank."
TIP_HIGH_RAM = (
    "High-RAM shape requires Colab Pro or Pro+. "
    "Ignored for L4 and TPU, which offer a single shape."
)
TIP_TIMEOUT = "Maximum time to wait for code execution to complete."
TIP_DRIVE_MOUNT = "Mounts your Google Drive to access files from Colab."
TIP_AUTH_OAUTH2 = "Sign in via browser. Recommended for most users."
