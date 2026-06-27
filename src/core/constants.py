"""Application-wide constants."""

APP_NAME = "CollabShell"
APP_VERSION = "1.0.0"

# ── Storage keys ──────────────────────────────────────────────────────────────
STORAGE_THEME = "colab_theme"
STORAGE_ONBOARDING_DONE = "colab_onboarding_done"
STORAGE_AUTH_METHOD = "colab_auth_method"
STORAGE_DEFAULT_GPU = "colab_default_gpu"
STORAGE_DEFAULT_TPU = "colab_default_tpu"
STORAGE_DEFAULT_TIMEOUT = "colab_default_timeout"
STORAGE_KEEP_ALIVE = "colab_keep_alive"
STORAGE_AUTO_STOP = "colab_auto_stop"
STORAGE_LOG_FORMAT = "colab_log_format"
STORAGE_DRIVE_MOUNT_PATH = "colab_drive_mount_path"
STORAGE_LOGTOSTDERR = "colab_logtostderr"

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
LBL_NEW_SESSION = "New Session"
LBL_QUICK_RUN = "Quick Run"
LBL_FILES = "Files"
LBL_SESSIONS = "Sessions"
LBL_EXECUTE = "Execute"
LBL_STOP = "Stop"
LBL_RESTART = "Restart Kernel"
LBL_UPLOAD = "Upload"
LBL_DOWNLOAD = "Download"
LBL_INSTALL = "Install Packages"
LBL_MOUNT_DRIVE = "Mount Drive"
LBL_AUTH_GCP = "Auth GCP"
LBL_OPEN_BROWSER = "Open in Browser"
LBL_EXPORT_LOG = "Export Log"
LBL_MANAGE_COMPUTE = "Manage Compute"
LBL_SIGN_IN = "Sign in to Google"
LBL_RE_AUTH = "Re-authenticate"
LBL_CHECK_UPDATES = "Check for Updates"

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
TIP_AUTH_OAUTH2 = "Sign in via browser. Recommended for most users."
TIP_AUTH_ADC = "Uses gcloud Application Default Credentials. For advanced users."
