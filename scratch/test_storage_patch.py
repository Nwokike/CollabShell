import os
import sys
from pathlib import Path

# Add src to path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from core.storage_patch import apply_storage_patches
import colab_cli.auth
import colab_cli.state
import colab_cli.history

print("Applying patches...")
apply_storage_patches()

print("TOKEN_CONFIG_PATH:", colab_cli.auth.TOKEN_CONFIG_PATH)
print("SettingsStore default path:", colab_cli.state.SettingsStore.__init__.__defaults__)
print("HistoryLogger default path:", colab_cli.history.HistoryLogger.__init__.__defaults__)

# Check if directory exists
project_root = Path(__file__).resolve().parent.parent
storage_dir = os.path.join(project_root, "storage")
print("Storage dir exists:", os.path.exists(storage_dir))
if os.path.exists(storage_dir):
    print("Contents:", os.listdir(storage_dir))
