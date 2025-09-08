import base64
from typing import Tuple, List

def _css_escape(text: str) -> str:
    return text.replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;")

def _rgba_to_hex(rgba) -> str:
    # If rgba is int (legacy), assume black
    if isinstance(rgba, int):
        return "#000000"
    elif isinstance(rgba, (list, tuple)) and len(rgba) >= 3:
        r, g, b = rgba[:3]
        return f"#{int(r):02X}{int(g):02X}{int(b):02X}"
    return "#000000"

def _is_dark(stroke_hex: str) -> bool:
    """Return True if the stroke color is dark (used for table borders)"""
    r, g, b = int(stroke_hex[1:3],16), int(stroke_hex[3:5],16), int(stroke_hex[5:7],16)
    luminance = 0.299*r + 0.587*g + 0.114*b
    return luminance < 128

def _build_page_absolute(page):
    width, height = page['width'], page['height']
    html = [f'<div class="page" style="position:relative;width:{width}px;height:{height}px;">']

    for el in page['elements']:
        x0,y0,x1,y1 = el.get('bbox',[0,0,0,0])
        if el['type'] == 'text':
            style = f"position:absolute;left:{x0}px;top:{y0}px;font-family:{el['font']['name']};font-size:{el['font']['size']}px;color:{el.get('color','#000')};"
            html.append(f'<div style="{style}">{_css_escape(el["text"])}</div>')

        elif el['type'] == 'rect':
            w = max(0, x1-x0)
            h = max(0, y1-y0)

            # Only draw dark/thin borders for table-like lines
            border_color = el.get('stroke','#000')
            border_style = 'solid' if _is_dark(border_color) else 'none'
            background = el.get('fill','transparent')
            thickness = el.get('thickness',1)
            
            style = f"position:absolute;left:{x0}px;top:{y0}px;width:{w}px;height:{h}px;"
            style += f"border:{thickness}px {border_style} {border_color};"
            style += f"background:{background};"
            html.append(f'<div style="{style}"></div>')

        elif el['type'] == 'image' and el.get('image_bytes'):
            b64 = base64.b64encode(el['image_bytes']).decode('ascii')
            style = f"position:absolute;left:{x0}px;top:{y0}px;width:{x1-x0}px;height:{y1-y0}px;"
            html.append(f'<img style="{style}" src="data:image/png;base64,{b64}"/>')

    html.append('</div>')
    css = ".page{background:white;box-shadow:0 0 8px rgba(0,0,0,.1);margin:16px auto;}"
    return "\n".join(html), css

def _build_page_semantic(page):
    # Minimal semantic flow
    lines = ["<section class=\"page-semantic\">"]
    for el in page['elements']:
        if el['type'] == 'text' and el.get('text','').strip():
            lines.append(f"<p class=\"t\">{_css_escape(el['text'])}</p>")
    lines.append("</section>")
    css = ".page-semantic{max-width:900px;margin:24px auto;padding:24px;background:#fff} .t{margin:0 0 4px;}"
    return "\n".join(lines), css

def build_from_pdf_layout(layout, mode: str = "absolute") -> Tuple[str,str,List[str],list]:
    warnings = []
    assets = []
    pages = layout.get('pages', [])
    html_pages = []
    css_all = []

    for i, page in enumerate(pages):
        if mode == 'semantic':
            h, c = _build_page_semantic(page)
        else:
            h, c = _build_page_absolute(page)
        html_pages.append(h)
        css_all.append(c)

    html = "\n".join(html_pages)
    css = "\n".join(css_all)
    return html, css, warnings, assets
