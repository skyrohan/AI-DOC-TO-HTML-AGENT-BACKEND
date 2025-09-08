import fitz  # PyMuPDF
import base64
from typing import Tuple, List

# --- UTILS ---

def _rgba_to_hex(rgba) -> str:
    """Convert PyMuPDF color value to hex string or 'transparent'."""
    if rgba is None:
        return "transparent"
    if isinstance(rgba, int):
        return "#000000"
    if isinstance(rgba, (list, tuple)):
        vals = list(rgba)
        if len(vals) >= 3:
            r, g, b = vals[:3]
            if all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in (r, g, b)):
                r, g, b = int(r * 255), int(g * 255), int(b * 255)
            else:
                r, g, b = int(r), int(g), int(b)
            # fully transparent
            if len(vals) == 4 and vals[3] == 0:
                return "transparent"
            return f"#{r:02X}{g:02X}{b:02X}"
    return "#000000"


def _css_escape(text: str) -> str:
    if not isinstance(text, str):
        text = str(text or "")
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def _luminance_from_hex(hexcol: str) -> float:
    """Return perceived luminance (0..255). Transparent = 255 (light)."""
    if not hexcol or hexcol == "transparent":
        return 255.0
    try:
        r = int(hexcol[1:3], 16)
        g = int(hexcol[3:5], 16)
        b = int(hexcol[5:7], 16)
        return 0.299*r + 0.587*g + 0.114*b
    except Exception:
        return 255.0


def _map_pdf_thickness_to_css(thickness: float, scale: float = 1.0) -> float:
    """Map PDF stroke thickness to CSS px. Keep sub-pixel values."""
    if not thickness:
        return 0.5
    css_px = float(thickness) * scale * 0.75
    return max(0.2, min(css_px, 3.0))


def _border_css_from(stroke_hex: str, thickness: float) -> str:
    """Return CSS border string from stroke + thickness."""
    css_th = _map_pdf_thickness_to_css(thickness)
    lum = _luminance_from_hex(stroke_hex)
    style = "solid" if lum <= 230 else "dotted"
    if stroke_hex == "transparent":
        return "none"
    return f"{css_th}px {style} {stroke_hex}"


# --- PDF LAYOUT EXTRACTION ---

def extract_layout(pdf_bytes: bytes):
    doc = fitz.open(stream=pdf_bytes, filetype='pdf')
    pages = []

    for page in doc:
        width, height = page.rect.width, page.rect.height
        elements = []

        # --- TEXT ---
        text_dict = page.get_text("dict")
        for block in text_dict.get("blocks", []):
            if block.get("type", 0) == 0:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        bbox = span.get("bbox") or [0, 0, 0, 0]
                        elements.append({
                            "type": "text",
                            "bbox": bbox,
                            "text": span.get("text", ""),
                            "font": {
                                "name": span.get("font", "sans-serif"),
                                "size": span.get("size", 10),
                                "bold": "Bold" in (span.get("font", "") or "")
                            },
                            "color": _rgba_to_hex(span.get("color", (0, 0, 0, 1)))
                        })

        # --- SHAPES ---
        for path in page.get_drawings():
            stroke = _rgba_to_hex(path.get("stroke", (0, 0, 0, 1)))
            fill = _rgba_to_hex(path.get("fill", (1, 1, 1, 0)))
            thickness = path.get("width", 1) or 1
            for item in path.get("items", []):
                kind = item[0]
                data = item[1]
                if kind == "re":
                    bbox = [data.x0, data.y0, data.x1, data.y1]
                    elements.append({
                        "type": "rect",
                        "bbox": bbox,
                        "stroke": stroke,
                        "fill": fill,
                        "thickness": float(thickness)
                    })
                elif kind == "l":
                    p0, p1 = item[1], item[2]
                    x0, y0 = float(p0[0]), float(p0[1])
                    x1, y1 = float(p1[0]), float(p1[1])
                    bbox = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
                    elements.append({
                        "type": "rect",
                        "bbox": bbox,
                        "stroke": stroke,
                        "fill": "transparent",
                        "thickness": float(thickness)
                    })

        # --- IMAGES ---
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.alpha:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                img_bytes = pix.tobytes("png")
                # use actual bbox from image rects
                rects = page.get_image_rects(xref)
                if rects:
                    r = rects[0]
                    bbox = [r.x0, r.y0, r.x1, r.y1]
                else:
                    bbox = [0, 0, pix.width, pix.height]
            except Exception:
                img_bytes = None
                bbox = [0, 0, 0, 0]
            elements.append({
                "type": "image",
                "bbox": bbox,
                "image_bytes": img_bytes
            })

        pages.append({"width": width, "height": height, "elements": elements})

    return {"pages": pages}


# --- HTML BUILDER ---

def _build_page_absolute(page, scale: float = 1.0):
    width, height = page["width"], page["height"]
    html = [f'<div class="page" style="position:relative;width:{width*scale}px;height:{height*scale}px;">']

    for el in page["elements"]:
        x0, y0, x1, y1 = el.get("bbox", [0, 0, 0, 0])
        x0s, y0s, x1s, y1s = x0*scale, y0*scale, x1*scale, y1*scale
        w, h = max(0.0, x1s - x0s), max(0.0, y1s - y0s)

        if el["type"] == "text":
            style = (
                f"position:absolute;"
                f"left:{x0s}px;top:{y0s - el['font']['size']*0.8}px;"
                f"font-family:{el['font']['name']};"
                f"font-size:{el['font']['size']}px;"
                f"color:{el.get('color','#000')};"
                f"line-height:{el['font']['size']*1.1}px;"
                f"white-space:pre;z-index:10;"
            )
            text = _css_escape(el.get("text", ""))
            html.append(f'<div style="{style}">{text}</div>')

        elif el["type"] == "rect":
            stroke = el.get("stroke", "transparent")
            fill = el.get("fill", "transparent")
            css_thickness = _map_pdf_thickness_to_css(el.get("thickness", 1.0), scale=scale)
            border_css = _border_css_from(stroke, css_thickness)

            style = (
                f"position:absolute;left:{x0s}px;top:{y0s}px;width:{w}px;height:{h}px;"
                f"background:{fill};z-index:1;"
            )
            if border_css != "none":
                style += f"border:{border_css};"
            html.append(f'<div style="{style}"></div>')

        elif el["type"] == "image" and el.get("image_bytes"):
            b64 = base64.b64encode(el["image_bytes"]).decode("ascii")
            style = (
                f"position:absolute;left:{x0s}px;top:{y0s}px;"
                f"width:{w}px;height:{h}px;"
                f"object-fit:contain;z-index:5;"
            )
            # guard against oversized logos
            if w > 300 or h > 300:
                style += "max-width:300px;max-height:300px;"
            html.append(f'<img style="{style}" src="data:image/png;base64,{b64}"/>')

    html.append("</div>")
    css = ".page{background:white;box-shadow:0 0 8px rgba(0,0,0,.06);margin:16px auto;}"
    return "\n".join(html), css


def build_from_pdf_bytes(pdf_bytes: bytes, mode: str="absolute", scale: float = 1.0) -> str:
    layout = extract_layout(pdf_bytes)
    html_pages, css_all = [], []

    for page in layout.get("pages", []):
        h, c = _build_page_absolute(page, scale=scale)
        html_pages.append(h)
        css_all.append(c)

    html_content = "\n".join(html_pages)
    css_content = "\n".join(css_all)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Document</title>
<style>
{css_content}
</style>
</head>
<body>
{html_content}
</body>
</html>
"""
