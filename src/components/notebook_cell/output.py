import flet as ft

from components.ansi_parser import parse_ansi_to_flet_text
from core import tokens
from core.theme import AppColors


def parse_outputs_to_controls(outputs: list) -> list[ft.Control]:
    output_controls = []
    for out in outputs:
        if len(output_controls) >= 1000:
            break
        if out.get("type") == "stream":
            is_err = out.get("name") == "stderr"
            text = out.get("text", "")
            output_controls.append(
                parse_ansi_to_flet_text(
                    raw_text=text, default_size=tokens.FONT_SM, is_error=is_err
                )
            )
        elif out.get("type") == "error":
            traceback = "\n".join(out.get("traceback", []))
            output_controls.append(
                parse_ansi_to_flet_text(
                    raw_text=traceback,
                    default_size=tokens.FONT_SM,
                    is_error=True,
                )
            )
        elif out.get("type") in ["execute_result", "display_data"]:
            data = out.get("data", {})
            if "image/png" in data:
                try:
                    b64_img = data["image/png"]
                    b64_img = b64_img.replace("\n", "").replace("\r", "")
                    output_controls.append(
                        ft.Container(
                            content=ft.Image(src_base64=b64_img, fit=ft.BoxFit.CONTAIN),
                            margin=ft.Margin(0, tokens.SPACE_SM, 0, tokens.SPACE_SM),
                        )
                    )
                except Exception as e:
                    output_controls.append(
                        ft.Text(f"Image Error: {e}", color=AppColors.ERROR)
                    )
            elif "text/markdown" in data:
                md = data["text/markdown"]
                if isinstance(md, list):
                    md = "".join(md)
                output_controls.append(
                    ft.Markdown(
                        str(md),
                        selectable=True,
                        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                    )
                )
            elif "text/html" in data:
                # Mirror colab_cli's render_display_data priority: html goes
                # through html2text (already a colab_cli dependency), then
                # falls back to the plain ANSI path when conversion fails.
                html = data["text/html"]
                if isinstance(html, list):
                    html = "".join(html)
                md_text = None
                try:
                    import html2text

                    md_text = html2text.html2text(str(html))
                except Exception:
                    md_text = None
                if md_text:
                    output_controls.append(
                        ft.Markdown(
                            md_text,
                            selectable=True,
                            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                        )
                    )
                elif "text/plain" in data:
                    output_controls.append(
                        parse_ansi_to_flet_text(
                            raw_text=data["text/plain"],
                            default_size=tokens.FONT_SM,
                        )
                    )
            elif "text/plain" in data:
                output_controls.append(
                    parse_ansi_to_flet_text(
                        raw_text=data["text/plain"],
                        default_size=tokens.FONT_SM,
                    )
                )
    return output_controls
