"""Built-in color schemes and themes for FletTerminal."""

from __future__ import annotations

from typing import Any

__all__ = ["BUILTIN_THEMES", "get_theme"]

BUILTIN_THEMES: dict[str, dict[str, str]] = {
    "Dracula": {
        "background": "#1E1F29",
        "foreground": "#F8F8F2",
        "cursor": "#FF79C6",
        "selection": "#44475A",
        "black": "#21222C",
        "red": "#FF5555",
        "green": "#50FA7B",
        "yellow": "#F1FA8C",
        "blue": "#BD93F9",
        "magenta": "#FF79C6",
        "cyan": "#8BE9FD",
        "white": "#F8F8F2",
    },
    "JetBrains Dark": {
        "background": "#1E1E2E",
        "foreground": "#CDD6F4",
        "cursor": "#F5E0DC",
        "selection": "#585B70",
        "black": "#45475A",
        "red": "#F38BA8",
        "green": "#A6E3A1",
        "yellow": "#F9E2AF",
        "blue": "#89B4FA",
        "magenta": "#F5C2E7",
        "cyan": "#94E2D5",
        "white": "#BAC2DE",
    },
    "Matrix Green": {
        "background": "#0D1117",
        "foreground": "#00FF66",
        "cursor": "#00FF66",
        "selection": "#163320",
        "black": "#0D1117",
        "red": "#FF5555",
        "green": "#00FF66",
        "yellow": "#FFFF00",
        "blue": "#0088FF",
        "magenta": "#FF00FF",
        "cyan": "#00FFFF",
        "white": "#FFFFFF",
    },
    "Colab Light": {
        "background": "#FFFFFF",
        "foreground": "#1F2430",
        "cursor": "#F97316",
        "selection": "#D6E4F0",
        "black": "#1F2430",
        "red": "#D93025",
        "green": "#188038",
        "yellow": "#B26A00",
        "blue": "#1A73E8",
        "magenta": "#C2185B",
        "cyan": "#00838F",
        "white": "#E8EAED",
    },
}


def get_theme(theme_name: str | None) -> dict[str, Any] | None:
    """Retrieve a built-in theme dictionary by name."""
    if not theme_name:
        return None
    return BUILTIN_THEMES.get(theme_name)
