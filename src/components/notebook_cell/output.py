import flet as ft

from components.ansi_parser import parse_ansi_to_flet_text
from core import tokens
from core.theme import AppColors

_IMAGE_MIMES = ("image/png", "image/jpeg", "image/gif", "image/webp")
_TEXT_MIMES = (
    "application/json",
    "application/javascript",
    "text/html",
    "text/markdown",
    "text/plain",
)


def _as_text(value) -> str:
    """nbformat stores text fields as a string OR a list of lines."""
    if isinstance(value, list):
        return "".join(str(v) for v in value)
    return str(value or "")


def _image_control(b64: str) -> ft.Control:
    b64 = str(b64).replace("\n", "").replace("\r", "")
    return ft.Container(
        content=ft.Image(src_base64=b64, fit=ft.BoxFit.CONTAIN),
        margin=ft.Margin(0, tokens.SPACE_SM, 0, tokens.SPACE_SM),
    )


def parse_outputs_to_controls(outputs: list) -> list[ft.Control]:
    output_controls = []
    for out in outputs:
        if len(output_controls) >= 1000:
            break
        otype = out.get("type")
        if otype == "stream":
            is_err = out.get("name") == "stderr"
            output_controls.append(
                parse_ansi_to_flet_text(
                    raw_text=_as_text(out.get("text", "")),
                    default_size=tokens.FONT_SM,
                    is_error=is_err,
                )
            )
        elif otype == "error":
            traceback = "\n".join(str(t) for t in out.get("traceback", []))
            output_controls.append(
                parse_ansi_to_flet_text(
                    raw_text=traceback,
                    default_size=tokens.FONT_SM,
                    is_error=True,
                )
            )
        elif otype == "clear_output":
            # Marker output: the renderer clears above this point.
            output_controls.append(ft.Container(height=0, content=ft.Text("")))
        elif otype in ("execute_result", "display_data", "update_display_data"):
            data = out.get("data", {}) or {}
            handled = False
            for mime in _IMAGE_MIMES:
                if mime in data:
                    try:
                        output_controls.append(_image_control(data[mime]))
                        handled = True
                    except Exception as e:
                        output_controls.append(
                            ft.Text(f"Image Error: {e}", color=AppColors.ERROR)
                        )
                        handled = True
                    break
            if not handled and "image/svg+xml" in data:
                # SVG is XML, not base64 — render the source as text.
                output_controls.append(
                    ft.Text(_as_text(data["image/svg+xml"])[:4000], size=tokens.FONT_XS)
                )
                handled = True
            if not handled:
                for mime in _TEXT_MIMES:
                    if mime in data:
                        text = _as_text(data[mime])
                        if mime == "application/json":
                            import json

                            try:
                                text = json.dumps(json.loads(text), indent=2)
                            except Exception:
                                pass
                        output_controls.append(
                            parse_ansi_to_flet_text(
                                raw_text=text, default_size=tokens.FONT_SM
                            )
                        )
                        handled = True
                        break
            if not handled:
                output_controls.append(
                    ft.Text("(unsupported output)", size=tokens.FONT_XS, italic=True)
                )
    return output_controls
