# Investigate 03 — in-session FAB options ("suggest runtime shape" must go)

Verdict: the ONLY creation-time-only entry in the in-session FAB is "Suggest
runtime shape for this notebook" (fab_menu.py:194-201). Everything else is valid
in-session. v2.1.2's fab_menu.py had no AI group at all; target = v2.1.2 menu +
"Rename Notebook" + AI group minus the hardware entry.

## Exact delete list
- `src/screens/session/fab_menu.py`: param `on_ai_suggest_hardware` (line 63) + the
  `if on_ai_suggest_hardware:` block (194-201)
- `src/screens/session/__init__.py`: kwarg at line 276
- `src/screens/session/notebook_view.py`: `_suggest_hardware` (577-616) + registry
  entry `"suggest_hardware"` (1197-1198)
- `src/services/cell_ai.py`: `HARDWARE_OPTIONS` (29-41) + the two `"hardware"`
  branches in `_model_messages` (114-121, 128-138) + docstring mentions
- Tests: `tests/screens/test_fab_mode_filtering.py:53,101,150`;
  `tests/services/test_cell_ai.py` hardware tests (~340-377)
- Comment-only mentions: `command_palette.py:5`, `docs/audit-08-ai-in-session.md`

## Keep (creation-time or display-only, NOT part of this feature)
`hardware_picker.py` (used by new_session_sheet from Home), settings
hardware_section.py, `ai_tools.create_session` accelerator params, hardware_badge/
shape_chip display, ai_quick.ask, cell-level AI actions, terminal explain.

## FAB menu inventory (valid in-session)
Terminal mode: New Terminal, Copy/Paste, Clear Terminal, theme presets, zoom,
blink/search. Notebook mode: Import, Rename, Export, Clear Outputs, Mount Drive,
Auth GCP, Open in Browser, View Logs. Shared: Manage Files, Restart Kernel,
Stop Session. AI group: Explain Terminal with AI, Ask AI about this cell,
Open Assistant (keep these three; drop only the hardware one).
