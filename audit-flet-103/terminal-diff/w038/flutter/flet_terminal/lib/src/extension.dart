import 'package:flet/flet.dart';
import 'package:flutter/widgets.dart';

import 'flet_terminal.dart';

class Extension extends FletExtension {
  @override
  Widget? createWidget(Key? key, Control control) {
    switch (control.type) {
      case "FletTerminal":
        return FletTerminalControl(control: control);
      default:
        return null;
    }
  }
}
