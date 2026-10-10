# 0.3.8

- **Host keyboard shortcuts, leak-free.** `Terminal`/`MobileTerminal` gain an `on_shortcut` event. Built-in combos are consumed on the Dart side via xterm's `onKeyEvent` hook — the highest-priority stage of xterm's key pipeline — so they never reach the PTY. Enabled only when `on_shortcut` is set; without a handler all keys flow to the terminal untouched.
- Combo set: `Ctrl/Cmd+Shift+T` (new_terminal), `+W` (close_terminal), `+1..9` (switch_terminal_N), `+F` (toggle_search), `+L` (clear), `+C` (copy), `+V` (paste), `+=` (zoom_in), `+-` (zoom_out), `+0` (zoom_reset), `Ctrl/Cmd+PageUp/PageDown` (prev/next_terminal), `F1` (help).
- New `ShortcutEvent` payload (`.shortcut` carries the machine name) exported from the package root.

# 0.2.2

- Updated default font size from 13px to 11px.
- Re-ordered virtual extra keys so arrow keys (`↑`, `↓`, `←`, `→`) come immediately after `ALT`.
- Hidden search bar by default (`show_search=False`), toggleable via settings menu.
- Intuitive collapse toggle button arrow states (`ARROW_DROP_UP` when open, `ARROW_DROP_DOWN` when collapsed).

# 0.2.1

- `Terminal.write()` and `write_async()` automatically route over the binary `DataChannel` (`pty`) fast-path whenever available, providing zero-latency output streaming for all applications.
- Built-in Zoom control: `MobileTerminal` now includes `zoom_in()`, `zoom_out()`, and `reset_zoom()` methods. The `ExtraKeysBar` settings menu features a one-line interactive font size row (`Font Size: 13px [ - ] [ + ] [ ↺ ]`) plus individual zoom menu items.
- Dynamic Checkmarks (`checked=True`): All options in the `ExtraKeysBar` settings menu (`Theme Presets`, `Cursor Style`, `Cursor Blink`, `Search Bar`) now display visual checkmarks indicating exactly what is currently selected, and dynamically check/uncheck whenever options are changed.

# 0.2.0

- `MobileTerminal` — new bundled wrapper with collapsible extra-keys bar, search, and settings popup (theme/cursor/blink) built-in.
- All `Terminal` properties and methods forwarded through `MobileTerminal` for drop-in compatibility.
- UI redesign: compact AppBar toolbar, SubmenuButton settings/demos, responsive layout.
- Search: now visibly selects the match and reports count via `on_selection_change`.
- Readiness signal simplified (`did_mount` + `data_channel_open` + `before_event`).
- `send_bytes` fallback buffers binary data instead of corrupting through string protocol.
- `search()` accepts optional `start` parameter for stepping through matches.

# 0.1.0

- Initial release of `flet-terminal` native GPU-accelerated terminal control.
- Full `xterm.js` feature parity: search, clipboard selection, title changes (`OSC 0/2`), audio/visual bell (`\a`).
- High-throughput binary `DataChannel` streaming (`send_bytes` / `on_bytes`).
- Sticky soft-keyboard modifiers (`CTRL`, `ALT`).
