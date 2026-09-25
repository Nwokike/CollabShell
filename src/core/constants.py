"""Application-wide constants."""

APP_NAME = "Colab Shell"
APP_FULL_NAME = "Colab Shell: Notebook & TTY"
APP_VERSION = "2.3.0"
APP_BUILD_NUMBER = 14
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
STORAGE_AUTH_METHOD = "colab_auth_method"
STORAGE_DEFAULT_GPU = "colab_default_gpu"
STORAGE_DEFAULT_TPU = "colab_default_tpu"
STORAGE_DEFAULT_TIMEOUT = "colab_default_timeout"
STORAGE_KEEP_ALIVE = "colab_keep_alive"
STORAGE_KEEP_ALIVE_ON_DISCONNECT = "colab_keep_alive_on_disconnect"
STORAGE_LOG_FORMAT = "colab_log_format"
STORAGE_DRIVE_MOUNT_PATH = "colab_drive_mount_path"
STORAGE_LOGTOSTDERR = "colab_logtostderr"
STORAGE_DEFAULT_HIGH_MEM = "colab_default_high_mem"
STORAGE_EXEC_ENV = "colab_exec_env"

# ── AI assistant ─────────────────────────────────────────────────────────────
STORAGE_AI_ENABLED = "colab_ai_enabled"
STORAGE_AI_TOOLS_ENABLED = "colab_ai_tools_enabled"
STORAGE_AI_MODEL = "colab_ai_model"
STORAGE_AI_MESSAGES = "colab_ai_messages"  # 2.3.0 single thread, read once
STORAGE_AI_CHATS = "colab_ai_chats"
STORAGE_AI_ACTIVE_CHAT = "colab_ai_active_chat"
STORAGE_AI_USED = "colab_ai_credits_used"
STORAGE_AI_WINDOW = "colab_ai_credits_window"
# Ad-earned credits: never expire, spent after the daily grant.
STORAGE_AI_BONUS = "colab_ai_credits_bonus"
# How much of the bonus has been charged, so a failed call can be refunded
# to the ad credits it actually came from.
STORAGE_AI_BONUS_SPENT = "colab_ai_credits_bonus_spent"

# ── Premium ────────────────────────────────────────────────────────────────
# Granted by either channel: Google Play Billing (default) or the Kiri License
# Worker (fallback for users Google billing cannot serve).
STORAGE_PREMIUM = "collab_premium"
STORAGE_PREMIUM_SOURCE = "collab_premium_source"
STORAGE_PREMIUM_PRODUCT = "collab_premium_product"
# The Kiri recovery ID — the user's way back in after clearing app data.
STORAGE_LICENSE_RECOVERY = "kiri_recovery_id"
# Android opt-in for the direct channel. The Play-distributed build uses
# Google Play Billing; the direct channel is here only for the user who
# tells us Play payment does not work for them.
STORAGE_LICENSE_DIRECT = "kiri_license_direct_optin"
STORAGE_LICENSE_TOKEN = "kiri_license_token"
STORAGE_LICENSE_PAID_THROUGH = "kiri_license_paid_through"

# ── Hardware options (from colab_cli.client.Accelerator) ──────────────────────
# Free tier: CPU (always), T4 GPU (limited), TPU v5e1/v6e1 (limited)
# Paid: L4, G4, A100, H100
GPU_OPTIONS = ["T4", "L4", "G4", "A100", "H100"]
TPU_OPTIONS = ["v5e1", "v6e1"]
HARDWARE_TYPES = ["CPU", "GPU", "TPU"]

# Free-tier indicators — show contextual tips to users
FREE_TIER_GPU = ["T4"]
FREE_TIER_TPU = ["v5e1"]
PAID_TIER_GPU = ["L4", "G4", "A100", "H100"]

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
ERR_QUOTA = (
    "You may not have quota for this accelerator. Try a different one or use CPU."
)
ERR_CLI_NOT_FOUND = "Google Colab CLI is not installed or not accessible."

# ── Help / tips (contextual guidance for non-developers) ──────────────────────
TIP_CPU = "CPU sessions are always free and available. Great for light work."
TIP_GPU_FREE = "T4 GPU is available on the free tier with usage limits."
TIP_GPU_PAID = "This GPU requires Colab Pro or Pay As You Go."
TIP_TPU_FREE = "TPU is available on the free tier with usage limits."
TIP_SESSION_NAME = "Optional — a random name will be generated if left blank."
TIP_KEEP_ALIVE = (
    "Keeps the VM running even when idle. The session auto-terminates after 24 hours."
)
TIP_TIMEOUT = "Maximum time to wait for code execution to complete."
TIP_DRIVE_MOUNT = "Mounts your Google Drive to access files from Colab."
TIP_HIGH_MEM = (
    "Not available on free Colab accounts (needs Pro or higher). Works for "
    "CPU, T4, G4, A100 and H100; L4 and TPU runtimes have a fixed shape."
)
TIP_EXEC_ENV = (
    "Secrets and settings your code can read on every run — one KEY=VALUE "
    "per line. Values stay on your device."
)
TIP_AUTH_OAUTH2 = "Sign in via browser. Recommended for most users."
TIP_AUTH_ADC = "Uses gcloud Application Default Credentials. For advanced users."
