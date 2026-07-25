# Release Notes

## Colab Shell v1.2.0 — Major Feature Release (Build 3)

**Colab Shell: Notebook & TTY** (`v1.2.0`) is a major release featuring a native PTY WebSockets terminal engine with multi-tab support, local LLM and TUI execution, Jupyter Notebook (.ipynb) import/export, instant output rendering, smart AdMob placements, and an in-memory Activity Terminal log viewer.

### 🔥 Major New Features & Architectural Upgrades

#### 1. Native Colab WebSocket PTY Terminal Engine (`flet-terminal`)
- **Direct Colab Terminal WebSocket Client** — Replaced legacy web proxies and HTML iframe embeds with a native PTY WebSocket terminal engine connecting directly to Google Colab's `/api/terminals` WebSocket endpoints.
- **Multi-Tab Terminal Workspace** — Open, manage, switch, and close multiple concurrent terminal tabs (`Terminal 1`, `Terminal 2`, etc.) inside active cloud runtimes.
- **Interactive TUI & Local LLM Support** — Full support for running interactive terminal apps, AI coding assistants (`opencode`), local LLMs (`ollama run llama3`), terminal multiplexers, and command line tools with custom soft keys (`ESC`, `TAB`, `CTRL`, `ALT`, Arrow Keys).
- **Terminal Themes & Customization** — Custom terminal themes (Matrix Green `#A6E22E`, Dracula, JetBrains Dark), cursor styles (Block, Underline, Bar), cursor blink toggles, font size zoom controls, output search bar, and 11px font rendering.
- **Distraction-Free Fullscreen Mode** — Single-tap fullscreen toggle hiding top navigation bars while preserving connection status indicators and tab switchers.

#### 2. Jupyter Notebook (.ipynb) Import/Export & Instant Output Rendering
- **Jupyter Notebook (.ipynb) Import & Export** — Import external `.ipynb` notebook files directly into active sessions, and export session code/markdown cells as valid `.ipynb` JSON notebooks.
- **Instant Output Cell Rendering & Dynamic Height** — Bound `output_panel_ref` to outer containers and dynamically recalculate output view heights (`min(max(total_lines * 20 + 16, 40), 220)`) during real-time streaming code execution.
- **Live Markdown Preview** — Instant toggle between Markdown cell editing and rendered preview mode.

#### 3. Smart Monetization & AdMob Enhancements
- **Harmonized AdMob Control Lifecycle** — Fixed `BannerAd` initialization by catching specific exception tuples matching DDGS `(ValueError, TypeError, OSError, RuntimeError, ConnectionError, ImportError)`, eliminating `Control must be added to the page first` Flutter bridge warnings and ensuring banner ads mount reliably.
- **Smart Inter-Cell Banner Ad Placements** — Automatically injects glass-styled AdMob banner ads after every 3 notebook cells (code or markdown) in long notebook sessions.
- **File Download Interstitial Ads** — Displays full-screen interstitial ads when users download files or folders from the Remote File Manager.

#### 4. Activity Terminal & Diagnostic Logging
- **Multi-Logger Memory Ring-Buffer** — Attached `MemoryLogHandler` across all app logger namespaces (`""`, `"colab"`, `"flet"`, `"router"`, `"services"`, `"core"`).
- **Activity Terminal Log Sheet** — Integrated a live troubleshooting Activity Terminal sheet in Settings styled with Matrix Green terminal fonts (`#A6E22E`, 11px) and single-tap clipboard copying (`ft.Clipboard().set`).

#### 5. CI/CD & Build Environment Parity
- **Flet Version Pinning** — Pinned dependencies in `pyproject.toml` to exact versions (`flet==0.85.3` and `flet-ads==0.85.3`) to prevent unpinned Flet 0.86.0 upgrades from targeting Python 3.14 on GitHub Actions build runners.
- **Branding & Assets** — Custom Windows setup installer wizard logos, app icon integration, and updated publisher metadata to *Kiri Research Labs* (`ng.kiri`).

---

## Colab Shell v1.1.0 — Major Update (Build 2)

**Colab Shell: Notebook & TTY** (`v1.1.0`) is a major release bringing full real-time interactive terminal emulation, robust multi-platform storage normalization, enhanced remote file management, and polished action workflows.

### 🔥 Major New Features & Architectural Upgrades

#### 1. Interactive PTY Terminal & Tabbed Workspace
- **Real-Time Web-Based Terminal (TTY)** — Integrated live interactive terminal sessions directly into the session workspace via Google Colab's `/api/terminals` WebSocket endpoints.
- **Tabbed Session Interface** — Seamlessly toggle between **Notebook** cell execution and **Terminal** shell tabs within an active cloud instance.
- **WebSocket Header & Protocol Engineering** — Resolved remote connection rejections by injecting `Origin: https://colab.research.google.com` and properly formatting subprotocols (`['colab-ws-token']`) across `tornado` proxy tunnels.

#### 2. Unified Storage & History Logging Infrastructure
- **Universal Storage Patching (`storage_patch.py`)** — Intercepted and wrapped `HistoryLogger.__init__`, `StateStore`, and `SettingsStore` to ensure all execution logs and session histories persist reliably inside `storage/history/` on both Android mobile devices and Linux desktop environments.
- **Full Backend Audit Logging** — Added automatic `HistoryLogger().log_event()` hooks across all core operations: `new_session`, `stop_session`, `exec_code`, `ls`, `upload`, `download`, and `rm`.
- **Instant Log Visibility** — Fixed previous issues where session history views displayed empty lists by eliminating split configuration directory paths.

#### 3. Interactive File Manager Improvements
- **Parent Directory Navigation** — Upgraded directory traversal using `posixpath.dirname` and `posixpath.normpath` to allow seamless browsing from subdirectories up to `/content` and root (`/`).
- **Instant UI Repainting** — Uploading (`upload`) or deleting (`rm`) files now automatically refreshes directory listings (`_load_files`) and forces immediate UI repainting (`page.update()`) so changes appear instantly.
- **Native OS File Picker & Folder Downloading** — Integrated `ft.FilePicker` so users can choose exact save destinations on their device without Android storage permission conflicts. Added comprehensive **Zip-and-Download** support for archiving and downloading entire remote directories.
- **Animated Progress Bars & Payload Sizes** — Replaced indeterminate loading spinners with sweeping `ft.ProgressBar` controls that accurately report total payload sizes during uploads and downloads.
- **Path Normalization** — Standardized POSIX path joining (`posixpath.normpath`) across all file operations to eliminate path double-slashes and clean up file transfers.

#### 4. Action Bar & Home Dashboard Refinements
- **Home Quick Actions Redesign** — Replaced ambiguous dashboard buttons with clear, action-oriented controls: **New Notebook**, **Quick Terminal**, and **Cloud Files**.
- **Intelligent New Session Routing** — Launching a new instance directly from the **Terminal**, **Files**, or **Notebooks** dashboard actions now preserves the user's intent, routing straight into that feature view as soon as provisioning completes.
- **Robust Modal & Dialog Management** — Eliminated UI freezing and unresponsive barriers across the app by replacing deprecated `page.pop_dialog()` calls with explicit `dialog.open = False` state management.
- **Live Output for Drive & GCP Auth** — Wired live execution streaming (`on_output=_action_output`) to **Mount Drive** and **Auth GCP** buttons, showing immediate authorization prompts and progress updates directly in the snackbar.
- **Clearer Labeling** — Updated the `Browser` action chip label to **`Colab Web`** for improved user clarity.
- **Google Play Title Compliance** — Updated official app branding to `Colab Shell: Notebook & TTY` (28 characters, adhering to Google Play's 30-character limit).

#### 5. Open Source Upstream Contribution
- Identified core gaps in history logging and path normalization within the upstream `google-colab-cli` library and submitted Pull Request [#79](https://github.com/googlecolab/google-colab-cli/pull/79) to improve stability across the broader ecosystem.

---

## Colab Shell v1.0.0 — Initial Release (Build 1)

Welcome to the initial launch of **Collab Shell**, an independent, premium client application for managing, monitoring, and running Google Colab cloud environments directly from your mobile device. Built with Flet on Flutter and Python, Collab Shell delivers a responsive, polished experience for working with Colab from Android.

### Highlights
- Manage the full session lifecycle from your phone: create, inspect, restart, and stop instances
- Choose CPU, GPU, or TPU runtime options with hardware-aware setup
- Work in notebook-style cells with code, markdown, outputs, and stdin support
- Run one-shot scripts, browse remote files, and transfer data to and from the VM
- Keep a history of activity and export logs in multiple formats
- Personalize the app with theme, keep-alive, and session preferences

### Core Features
#### 1. Session Lifecycle & Accelerator Control
- **Accelerator Selection** — Provision GPU tiers (`T4` on the free tier; `L4`, `G4`, `A100`, `H100` on Pro/Pro+) or TPU models (`v5e1`, `v6e1`) to handle deep learning, AI inference, and high-performance computing.
- **Kernel Management** — Start new instances with custom names, check active runtime statuses, restart Python kernels to clear variables, and stop or terminate instances to release compute quota.
- **Active Keep-Alive Daemon** — Enable background pings every 60 seconds to help prevent Google from shutting down your VM due to idle timeouts.

#### 2. Interactive Notebook Cell Editor
- **Jupyter-Style Cells** — Add, edit, delete, and reorder Code and Markdown cells.
- **Rich Output Console** — Parse colorized ANSI logs, output streams, execution traces, and view inline generated images such as Matplotlib charts.
- **Interactive Stdin Inputs** — Support interactive code prompts through clean pop-up dialog overlays when the remote kernel requests user input.
- **Google Cloud & Drive Integration** — Mount your personal Google Drive filesystem directly to the VM path (`/content/drive`) or propagate credentials (GCP authentication) with one click.

#### 3. Remote File Browser & Event Logging
- **Virtual Directory Navigation** — Navigate the remote Linux filesystem of your Google Colab instance.
- **File Transfers** — Upload local datasets and scripts from your mobile storage, download remote output assets to your local device `Downloads` folder, and delete files on the instance.
- **Event Trace Logs** — Keep an audit trail of session creations, script executions, file transfers, and system automations.
