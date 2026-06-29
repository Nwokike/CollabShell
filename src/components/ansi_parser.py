import flet as ft
from rich.ansi import AnsiDecoder

# Reusable decoder instance
_decoder = AnsiDecoder()

def _rich_color_to_hex(color):
    """Convert a rich.color.Color to a hex string for Flet, if possible."""
    if not color:
        return None
    # rich colors can be standard (0-15), 8-bit (0-255), or truecolor
    if color.triplet:
        r, g, b = color.triplet
        return f"#{r:02x}{g:02x}{b:02x}"
    
    if color.number is not None:
        # A basic mapping of 16 terminal colors to pleasing hex values
        cmap = {
            0: "#000000", 1: "#cc0000", 2: "#4e9a06", 3: "#c4a000", 
            4: "#3465a4", 5: "#75507b", 6: "#06989a", 7: "#d3d7cf",
            8: "#555753", 9: "#ef2929", 10: "#8ae234", 11: "#fce94f", 
            12: "#729fcf", 13: "#ad7fa8", 14: "#34e2e2", 15: "#eeeeec"
        }
        return cmap.get(color.number, None)
    return None

def parse_ansi_to_flet_text(
    raw_text: str, 
    default_size: int = 12, 
    default_color: str = "#F8F8F2",
    is_error: bool = False
) -> ft.Text:
    """
    Takes a raw ANSI string containing \x1b codes, parses it with rich,
    and returns a Flet ft.Text component with properly colored TextSpans.
    """
    if is_error:
        default_color = "#FF5555" # AppColors.ERROR equivalent
        
    # Clean carriage returns: simulate terminal overwrite by taking the last segment per line
    lines = raw_text.split('\n')
    cleaned_lines = []
    for line in lines:
        segments = [s for s in line.split('\r') if s.strip()]
        if segments:
            cleaned_lines.append(segments[-1])
        else:
            cleaned_lines.append("")
            
    cleaned_text = '\n'.join(cleaned_lines)

    if not cleaned_text.strip():
        return ft.Text(cleaned_text, size=default_size, font_family="RobotoMono", color=default_color)

    decoded_lines = list(_decoder.decode(cleaned_text))
    
    flet_spans = []
    for line_idx, rich_text in enumerate(decoded_lines):
        if line_idx > 0:
            flet_spans.append(ft.TextSpan("\n", style=ft.TextStyle(color=default_color)))
            
        if not rich_text.spans:
            flet_spans.append(ft.TextSpan(
                rich_text.plain, 
                style=ft.TextStyle(color=default_color)
            ))
            continue
            
        last_idx = 0
        spans = sorted(rich_text.spans, key=lambda s: s.start)
        
        for span in spans:
            # Unstyled text before this span
            if span.start > last_idx:
                flet_spans.append(ft.TextSpan(
                    rich_text.plain[last_idx:span.start],
                    style=ft.TextStyle(color=default_color)
                ))
                
            # Styled text
            flet_color = _rich_color_to_hex(span.style.color) or default_color
            weight = ft.FontWeight.BOLD if span.style.bold else None
            italic = span.style.italic
            bgcolor = _rich_color_to_hex(span.style.bgcolor)
            
            flet_spans.append(ft.TextSpan(
                rich_text.plain[span.start:span.end],
                style=ft.TextStyle(
                    color=flet_color, 
                    weight=weight, 
                    italic=italic,
                    bgcolor=bgcolor
                )
            ))
            last_idx = span.end
            
        # Remaining unstyled text
        if last_idx < len(rich_text.plain):
            flet_spans.append(ft.TextSpan(
                rich_text.plain[last_idx:],
                style=ft.TextStyle(color=default_color)
            ))

    return ft.Text(
        spans=flet_spans,
        size=default_size,
        font_family="RobotoMono",
        no_wrap=False
    )
