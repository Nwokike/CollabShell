import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:flet/flet.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:xterm/xterm.dart' as qt;

class FletTerminalControl extends StatefulWidget {
  final Control control;

  const FletTerminalControl({
    super.key,
    required this.control,
  });

  @override
  State<FletTerminalControl> createState() => _FletTerminalControlState();
}

class _FletTerminalControlState extends State<FletTerminalControl> {
  late final qt.Terminal _terminal;
  final qt.TerminalController _terminalController = qt.TerminalController();
  final FocusNode _focusNode = FocusNode();
  final ScrollController _scrollController = ScrollController();
  DataChannel? _channel;
  StreamSubscription<Uint8List>? _channelSub;
  Timer? _blinkTimer;
  Timer? _selectionDebounce;
  bool _blinkOn = true;
  bool? _syncedBlink;
  // Sticky-bottom: while the user is at (or near) the bottom we follow new
  // output; once they scroll up — e.g. to highlight text further up — every
  // rebuild stops yanking the view back down.
  bool _pinnedToBottom = true;

  // Host-level shortcuts consumed BEFORE xterm's input handler, so the key
  // combination never reaches the PTY. TerminalView.onKeyEvent has the
  // highest priority in xterm's key pipeline (it runs before the shortcut
  // manager and the terminal's own input handling); returning
  // KeyEventResult.handled swallows the event entirely.
  static final Map<LogicalKeyboardKey, String> _ctrlShiftShortcuts =
      <LogicalKeyboardKey, String>{
    LogicalKeyboardKey.keyT: "new_terminal",
    LogicalKeyboardKey.keyW: "close_terminal",
    LogicalKeyboardKey.keyF: "toggle_search",
    LogicalKeyboardKey.keyL: "clear",
    LogicalKeyboardKey.keyC: "copy",
    LogicalKeyboardKey.keyV: "paste",
    LogicalKeyboardKey.equal: "zoom_in",
    LogicalKeyboardKey.minus: "zoom_out",
    LogicalKeyboardKey.digit0: "zoom_reset",
    LogicalKeyboardKey.digit1: "switch_terminal_1",
    LogicalKeyboardKey.digit2: "switch_terminal_2",
    LogicalKeyboardKey.digit3: "switch_terminal_3",
    LogicalKeyboardKey.digit4: "switch_terminal_4",
    LogicalKeyboardKey.digit5: "switch_terminal_5",
    LogicalKeyboardKey.digit6: "switch_terminal_6",
    LogicalKeyboardKey.digit7: "switch_terminal_7",
    LogicalKeyboardKey.digit8: "switch_terminal_8",
    LogicalKeyboardKey.digit9: "switch_terminal_9",
  };

  KeyEventResult _handleShortcutKey(FocusNode node, KeyEvent event) {
    // Only react to the initial press; repeats and releases flow through
    // untouched so held keys keep typing. Returning `ignored` lets xterm
    // process the key exactly as if this hook did not exist.
    if (event is! KeyDownEvent) return KeyEventResult.ignored;
    // Consume host shortcuts only when the Python side listens for them —
    // otherwise a Terminal without an on_shortcut handler would silently
    // swallow standard terminal key combos.
    if (!widget.control.hasEventHandler("shortcut")) {
      return KeyEventResult.ignored;
    }

    final kb = HardwareKeyboard.instance;
    final ctrl = kb.isControlPressed || kb.isMetaPressed;
    final shift = kb.isShiftPressed;
    final key = event.logicalKey;

    String? name;
    if (key == LogicalKeyboardKey.f1 && !ctrl && !shift && !kb.isAltPressed) {
      name = "help";
    } else if (ctrl && !shift &&
        (key == LogicalKeyboardKey.pageUp || key == LogicalKeyboardKey.pageDown)) {
      name = key == LogicalKeyboardKey.pageUp ? "prev_terminal" : "next_terminal";
    } else if (ctrl && shift) {
      name = _ctrlShiftShortcuts[key];
    }
    if (name == null) return KeyEventResult.ignored;

    widget.control.triggerEvent("shortcut", {"shortcut": name});
    return KeyEventResult.handled;
  }


  @override
  void initState() {
    super.initState();
    widget.control.addInvokeMethodListener(_handleMethodCall);
    widget.control.triggerEvent("mount", "");

    final maxLines = widget.control.getInt("scrollback", 10000)!;
    _terminal = qt.Terminal(maxLines: maxLines);
    _syncBlink(widget.control.getBool("cursor_blink", true)!);
    _scrollController.addListener(_updatePinned);

    // Surface real user selections (long-press word select, drag select) to
    // Python. Previously selection_change only fired from the search method.
    _terminalController.addListener(_onSelectionChanged);

    // Setup input forwarding from terminal to Python with sticky modifiers support
    _terminal.onOutput = (String output) {
      bool ctrl = widget.control.getBool("ctrl_active", false)!;
      bool alt = widget.control.getBool("alt_active", false)!;

      String processed = output;
      bool changed = false;

      if (ctrl && processed.length == 1) {
        int code = processed.codeUnitAt(0);
        if (code >= 97 && code <= 122) {
          // a-z
          processed = String.fromCharCode(code - 96);
          changed = true;
        } else if (code >= 65 && code <= 90) {
          // A-Z
          processed = String.fromCharCode(code - 64);
          changed = true;
        }
      }

      if (alt) {
        processed = '\x1b$processed';
        changed = true;
      }

      if (changed) {
        widget.control.updateProperties({
          "ctrl_active": false,
          "alt_active": false,
        }, dart: true, python: true, notify: true);

        widget.control.triggerEvent("modifier_reset", "");
      }

      if (_channelSub != null && _channel != null) {
        _channel!.send(Uint8List.fromList(utf8.encode(processed)));
      } else {
        widget.control.triggerEvent("data", processed);
      }
    };

    // Forward terminal window title changes (OSC 0 / OSC 2)
    _terminal.onTitleChange = (String title) {
      widget.control.triggerEvent("title_change", title);
    };

    // Forward terminal bell notifications (\a)
    _terminal.onBell = () {
      widget.control.triggerEvent("bell", "");
    };

    // Setup resize forwarding to Python
    _terminal.onResize = (width, height, pixelWidth, pixelHeight) {
      widget.control.triggerEvent(
          "resize",
          jsonEncode({
            "cols": width,
            "rows": height,
          }));
    };
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_channelSub != null) return; // initialize lazily once per spec

    try {
      final ch = FletBackend.of(context).openDataChannel();
      _channel = ch;
      _channelSub = ch.messages.listen((bytes) {
        if (mounted) {
          _terminal.write(utf8.decode(bytes, allowMalformed: true));
          // Follow new output only while the user is pinned to the bottom.
          if (_pinnedToBottom) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              if (mounted && _pinnedToBottom) {
                _scrollToBottom();
              }
            });
          }
        }
      });

      widget.control.triggerEvent("data_channel_open", {
        "channel_name": "pty",
        "channel_id": ch.id,
      });
    } catch (e) {
      debugPrint("[FletTerminal] Failed to initialize DataChannel in didChangeDependencies: $e");
    }
  }

  void _onSelectionChanged() {
    // Debounce: drag-select fires a controller notification per pixel moved;
    // forwarding each one to Python floods the bridge and re-renders the
    // host panel mid-drag. One event per 150 ms of quiet is plenty for both
    // the search counter and copy flows.
    _selectionDebounce?.cancel();
    _selectionDebounce = Timer(const Duration(milliseconds: 150), () {
      if (!mounted) return;
      final selection = _terminalController.selection;
      final hasSelection = selection != null;
      widget.control.triggerEvent(
        "selection_change",
        jsonEncode({
          "has_selection": hasSelection,
          "text": hasSelection ? _terminal.buffer.getText(selection) : "",
        }),
      );
    });
  }

  /// Tracks whether the user is still at the bottom of the scrollback.
  /// Called on every scroll offset change; anything beyond a small epsilon
  /// above the max extent means they scrolled up deliberately.
  void _updatePinned() {
    if (_scrollController.hasClients) {
      final pos = _scrollController.position;
      _pinnedToBottom = pos.pixels >= pos.maxScrollExtent - 40;
    }
  }

  Future<dynamic> _handleMethodCall(String name, dynamic args) async {
    if (name == "write") {
      if (mounted) {
        _terminal.write(args["data"] ?? "");
      }
    } else if (name == "clear") {
      if (mounted) {
        _terminal.buffer.clearScrollback();
        _terminal.buffer.clear();
      }
    } else if (name == "focus") {
      _focusNode.requestFocus();
    } else if (name == "clear_selection") {
      _terminalController.clearSelection();
    } else if (name == "get_selection") {
      final selection = _terminalController.selection;
      if (selection == null) return "";
      return _terminal.buffer.getText(selection);
    } else if (name == "paste") {
      final data = await Clipboard.getData(Clipboard.kTextPlain);
      if (data != null && data.text != null && data.text!.isNotEmpty) {
        if (_channelSub != null && _channel != null) {
          _channel!.send(Uint8List.fromList(utf8.encode(data.text!)));
        } else {
          widget.control.triggerEvent("data", data.text!);
        }
      }
    } else if (name == "select_all") {
      if (mounted) {
        _terminalController.setSelection(
          _terminal.buffer.createAnchor(
            0,
            _terminal.buffer.height - _terminal.viewHeight,
          ),
          _terminal.buffer.createAnchor(
            _terminal.viewWidth,
            _terminal.buffer.height - 1,
          ),
          mode: qt.SelectionMode.line,
        );
      }
    } else if (name == "search") {
      final query = args["query"] as String?;
      final start = (args["start"] as int? ?? 0);
      final direction = (args["direction"] as String? ?? "next");
      if (query != null && query.isNotEmpty && mounted) {
        final fullText = _terminal.buffer.getText();
        final lower = fullText.toLowerCase();
        final needle = query.toLowerCase();

        // Count every occurrence (not just the first).
        int count = 0;
        int from = 0;
        while (from != -1) {
          from = lower.indexOf(needle, from);
          if (from != -1) {
            count++;
            from += needle.length;
          }
        }

        // Locate the match to highlight. "next" finds the first match at or
        // after `start` (wrapping to the first); "prev" finds the last match
        // strictly before `start` (wrapping to the last).
        int index = -1;
        if (direction == "prev") {
          int cursor = 0;
          int lastBefore = -1;
          while (cursor != -1) {
            cursor = lower.indexOf(needle, cursor);
            if (cursor == -1) break;
            if (cursor < start) {
              lastBefore = cursor;
              cursor += needle.length;
            } else {
              break;
            }
          }
          if (lastBefore != -1) {
            index = lastBefore;
          } else {
            // Wrap to the final occurrence in the buffer.
            int wrap = -1;
            int c = 0;
            while (c != -1) {
              c = lower.indexOf(needle, c);
              if (c != -1) {
                wrap = c;
                c += needle.length;
              }
            }
            index = wrap;
          }
        } else {
          index = lower.indexOf(needle, start);
          if (index == -1) index = lower.indexOf(needle);
        }

        if (index != -1) {
          // Map the string offset to grid (col,row) so we can select the
          // matched run. xterm has no find engine, so we surface the match by
          // selecting it (visible highlight via the `selection` theme color).
          final before = fullText.substring(0, index);
          final startRow = before.split('\n').length - 1;
          final startCol = before.length - before.lastIndexOf('\n') - 1;
          final endRow = fullText.substring(0, index + query.length).split('\n').length - 1;
          final endCol = (index + query.length) -
              fullText.substring(0, index + query.length).lastIndexOf('\n') - 1;

          _terminalController.setSelection(
            _terminal.buffer.createAnchor(startCol, startRow),
            _terminal.buffer.createAnchor(endCol, endRow),
            mode: qt.SelectionMode.line,
          );
          widget.control.triggerEvent(
            "selection_change",
            jsonEncode({
              "query": query,
              "found": true,
              "count": count,
              "index": index,
            }),
          );
        } else {
          widget.control.triggerEvent(
            "selection_change",
            jsonEncode({
              "query": query,
              "found": false,
              "count": 0,
              "index": -1,
            }),
          );
        }
      }
    }
    return null;
  }

  qt.TerminalTheme _parseTheme(Map<dynamic, dynamic>? themeProps) {
    const d = qt.TerminalThemes.defaultTheme;
    if (themeProps == null) return d;

    Color parseColor(String key, Color fallback) {
      if (themeProps.containsKey(key)) {
        final val = themeProps[key];
        if (val is String) {
          final clean = val.replaceFirst('#', '').replaceFirst('0x', '');
          final hex = int.tryParse(clean, radix: 16);
          if (hex != null) {
            if (clean.length == 6) {
              if (key == "selection" || key == "searchHitBackground" || key == "searchHitBackgroundCurrent") {
                return Color(hex | 0x66000000);
              }
              return Color(hex | 0xFF000000);
            }
            return Color(hex);
          }
        } else if (val is int) {
          return Color(val);
        }
      }
      return fallback;
    }

    return qt.TerminalTheme(
      cursor: parseColor("cursor", d.cursor),
      selection: parseColor("selection", d.selection),
      foreground: parseColor("foreground", d.foreground),
      background: parseColor("background", d.background),
      black: parseColor("black", d.black),
      white: parseColor("white", d.white),
      red: parseColor("red", d.red),
      green: parseColor("green", d.green),
      yellow: parseColor("yellow", d.yellow),
      blue: parseColor("blue", d.blue),
      magenta: parseColor("magenta", d.magenta),
      cyan: parseColor("cyan", d.cyan),
      brightBlack: parseColor("brightBlack", d.brightBlack),
      brightRed: parseColor("brightRed", d.brightRed),
      brightGreen: parseColor("brightGreen", d.brightGreen),
      brightYellow: parseColor("brightYellow", d.brightYellow),
      brightBlue: parseColor("brightBlue", d.brightBlue),
      brightMagenta: parseColor("brightMagenta", d.brightMagenta),
      brightCyan: parseColor("brightCyan", d.brightCyan),
      brightWhite: parseColor("brightWhite", d.brightWhite),
      searchHitBackground: parseColor("searchHitBackground", d.searchHitBackground),
      searchHitBackgroundCurrent: parseColor("searchHitBackgroundCurrent", d.searchHitBackgroundCurrent),
      searchHitForeground: parseColor("searchHitForeground", d.searchHitForeground),
    );
  }

  qt.TerminalStyle _parseStyle() {
    final fontFamily = widget.control.getString("font_family", "JetBrains Mono")!;
    final fontSize = widget.control.getDouble("font_size", 11.0)!;
    return qt.TerminalStyle(
      fontFamily: fontFamily,
      fontSize: fontSize,
    );
  }

  qt.TerminalCursorType _parseCursorType(String? type) {
    if (type == "underline") return qt.TerminalCursorType.underline;
    if (type == "bar" || type == "verticalBar") return qt.TerminalCursorType.verticalBar;
    return qt.TerminalCursorType.block;
  }

  @override
  Widget build(BuildContext context) {
    final themeMap = widget.control.get<Map>("theme") ?? (widget.control.properties["theme"] as Map?);
    final theme = _parseTheme(themeMap);
    final style = _parseStyle();
    final cursorType = _parseCursorType(widget.control.getString("cursor_style"));
    final cursorBlink = widget.control.getBool("cursor_blink", true)!;
    if (cursorBlink != _syncedBlink) {
      _syncedBlink = cursorBlink;
      _syncBlink(cursorBlink);
    }
    final autofocus = widget.control.getBool("auto_focus", true)!;
    final readOnly = widget.control.getBool("read_only", false)!;

    final media = MediaQuery.of(context);
    final isMobile = media.size.width < 600;

    Widget termView = qt.TerminalView(
      _terminal,
      controller: _terminalController,
      scrollController: _scrollController,
      focusNode: _focusNode,
      theme: theme,
      textStyle: style,
      autofocus: autofocus,
      readOnly: readOnly,
      cursorType: cursorType,
      alwaysShowCursor: false,
      deleteDetection: isMobile,
      keyboardType: TextInputType.text,
      onKeyEvent: _handleShortcutKey,
      onSecondaryTapUp: (details, offset) async {
        if (_terminalController.selection != null) {
          final selectedText = _terminal.buffer.getText(_terminalController.selection!);
          if (selectedText.isNotEmpty) {
            await Clipboard.setData(ClipboardData(text: selectedText));
            _terminalController.clearSelection();
            widget.control.triggerEvent("copy", selectedText);
            return;
          }
        }
        final data = await Clipboard.getData(Clipboard.kTextPlain);
        if (data != null && data.text != null && data.text!.isNotEmpty) {
          if (_channelSub != null && _channel != null) {
            _channel!.send(Uint8List.fromList(utf8.encode(data.text!)));
          } else {
            widget.control.triggerEvent("data", data.text!);
          }
        }
      },
    );

    final bottomInset = media.viewInsets.bottom;

    return LayoutControl(
      control: widget.control,
      child: RepaintBoundary(
        child: LayoutBuilder(
          builder: (context, constraints) {
            double width = constraints.maxWidth;
            double height = constraints.maxHeight;
            if (width.isInfinite || width <= 0) {
              width = media.size.width > 0 ? media.size.width : 800.0;
            }
            if (height.isInfinite || height <= 0) {
              height = media.size.height > 0 ? (media.size.height - 120.0).clamp(200.0, 2000.0) : 500.0;
            }

            Widget currentView = termView;
            if (bottomInset > 0) {
              // Only snap to the bottom when the user hasn't deliberately
              // scrolled up (e.g. while highlighting text). Previously this
              // fired on every rebuild with the keyboard open, which made
              // scrollback unreachable during selection.
              if (_pinnedToBottom) {
                WidgetsBinding.instance.addPostFrameCallback((_) {
                  if (mounted && _pinnedToBottom) {
                    _scrollToBottom();
                  }
                });
              }
              if (constraints.maxHeight.isInfinite || constraints.maxHeight + bottomInset >= media.size.height - 80.0) {
                currentView = Padding(
                  padding: EdgeInsets.only(bottom: bottomInset),
                  child: currentView,
                );
              }
            }

            if (constraints.maxWidth.isInfinite || constraints.maxHeight.isInfinite) {
              return SizedBox(
                width: width,
                height: height,
                child: currentView,
              );
            }
            return currentView;
          },
        ),
      ),
    );
  }

  void _scrollToBottom() {
    if (_scrollController.hasClients) {
      _scrollController.jumpTo(_scrollController.position.maxScrollExtent);
    }
  }

  /// Drives the cursor blink by toggling the terminal's cursor-visibility
  /// mode on a periodic timer. xterm has no built-in blink: `alwaysShowCursor`
  /// only *adds* visibility and `cursorVisibleMode` defaults to true, so the
  /// cursor never actually hid. Toggling `cursorVisibleMode` (and forcing a
  /// repaint via `notifyListeners`, since the setter alone doesn't notify) is
  /// what produces a real blink. When blinking is disabled the cursor is
  /// restored to always-visible.
  void _syncBlink(bool blink) {
    _blinkTimer?.cancel();
    _blinkTimer = null;
    if (blink) {
      _blinkOn = true;
      _terminal.setCursorVisibleMode(true);
      _blinkTimer = Timer.periodic(const Duration(milliseconds: 530), (_) {
        if (!mounted) return;
        _blinkOn = !_blinkOn;
        _terminal.setCursorVisibleMode(_blinkOn);
        _terminal.notifyListeners();
      });
    } else {
      _terminal.setCursorVisibleMode(true);
      _terminal.notifyListeners();
    }
  }

  @override
  void dispose() {
    _blinkTimer?.cancel();
    _blinkTimer = null;
    _selectionDebounce?.cancel();
    _selectionDebounce = null;
    widget.control.removeInvokeMethodListener(_handleMethodCall);
    _terminalController.removeListener(_onSelectionChanged);
    _scrollController.removeListener(_updatePinned);
    _channelSub?.cancel();
    _channel?.close();
    _focusNode.dispose();
    _scrollController.dispose();
    _terminalController.dispose();
    super.dispose();
  }
}
