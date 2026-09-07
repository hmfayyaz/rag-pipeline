"""Generate a single PDF from the F2 platform design markdown with embedded images."""

from __future__ import annotations

import base64
import re
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

DOCS_DIR = Path(__file__).resolve().parent
MD_FILE = DOCS_DIR / "f2-platform-design.md"
PDF_FILE = DOCS_DIR / "f2-platform-design.pdf"
UPDATED_PDF_FILE = DOCS_DIR / "f2-platform-design-updated.pdf"
IMAGES_DIR = DOCS_DIR / "images"


def embed_images_as_base64(html: str) -> str:
    """Replace relative image paths with base64 data URIs for reliable PDF rendering."""
    image_count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal image_count
        image_count += 1
        alt, src = match.group(1), match.group(2)
        img_path = (DOCS_DIR / src).resolve()
        if not img_path.exists():
            return match.group(0)
        mime = "image/png" if img_path.suffix.lower() == ".png" else "image/jpeg"
        data = base64.b64encode(img_path.read_bytes()).decode("ascii")
        css_class = "diagram diagram-first" if image_count == 1 else "diagram"
        return f'<img alt="{alt}" src="data:{mime};base64,{data}" class="{css_class}" />'

    html = re.sub(r'<img alt="([^"]*)" src="([^"]+)" />', replace, html)
    # Push the component table after the first diagram to page 2
    html = re.sub(r"<table>", '<table class="page-break-before">', html, count=1)
    return html


def build_html(md_content: str) -> str:
    html_body = markdown.markdown(
        md_content,
        extensions=["tables", "fenced_code", "toc", "sane_lists"],
    )
    html_body = embed_images_as_base64(html_body)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>F2 Platform Design Document</title>
  <style>
    @page {{
      size: A4;
      margin: 20mm 18mm 22mm 18mm;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: "Segoe UI", Calibri, Arial, sans-serif;
      font-size: 10.5pt;
      line-height: 1.45;
      color: #1a1a1a;
      max-width: 100%;
    }}
    h1 {{
      font-size: 20pt;
      color: #0f2b46;
      border-bottom: 3px solid #0f2b46;
      padding-bottom: 6px;
      margin: 0 0 6px 0;
      page-break-after: avoid;
    }}
    h2 {{
      font-size: 14pt;
      color: #0f2b46;
      border-bottom: 1px solid #c8d6e0;
      padding-bottom: 3px;
      margin-top: 14px;
      margin-bottom: 6px;
      page-break-after: avoid;
    }}
    h3 {{
      font-size: 11pt;
      color: #1a4a6e;
      margin-top: 10px;
      margin-bottom: 4px;
      page-break-after: avoid;
    }}
    h4 {{
      font-size: 11pt;
      color: #333;
      margin-top: 16px;
      page-break-after: avoid;
    }}
    p, li {{ margin: 0 0 4px 0; }}
    ul, ol {{ margin: 4px 0 6px 0; padding-left: 22px; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 12px 0 16px 0;
      font-size: 9.5pt;
      page-break-inside: avoid;
    }}
    th {{
      background: #0f2b46;
      color: #fff;
      text-align: left;
      padding: 7px 8px;
      font-weight: 600;
    }}
    td {{
      border: 1px solid #d0d8de;
      padding: 6px 8px;
      vertical-align: top;
    }}
    tr:nth-child(even) td {{ background: #f5f8fa; }}
    code {{
      font-family: Consolas, "Courier New", monospace;
      font-size: 9pt;
      background: #f0f4f8;
      padding: 1px 4px;
      border-radius: 3px;
    }}
    pre {{
      background: #f0f4f8;
      border: 1px solid #d0d8de;
      border-radius: 4px;
      padding: 10px 12px;
      font-size: 8.5pt;
      line-height: 1.35;
      overflow-x: auto;
      page-break-inside: avoid;
      white-space: pre-wrap;
      word-wrap: break-word;
    }}
    pre code {{
      background: none;
      padding: 0;
    }}
    img.diagram {{
      display: block;
      max-width: 100%;
      height: auto;
      margin: 10px auto;
      page-break-inside: avoid;
    }}
    img.diagram-first {{
      max-height: 300px;
      width: auto;
      max-width: 100%;
      margin: 8px auto 6px auto;
      page-break-before: avoid;
      page-break-after: avoid;
    }}
    .page-break-before {{
      page-break-before: always;
    }}
    hr {{
      border: none;
      border-top: 1px solid #d0d8de;
      margin: 10px 0;
    }}
    strong {{ color: #0f2b46; }}
    a {{ color: #1a6fb5; text-decoration: none; }}
    .toc ul {{ list-style: none; padding-left: 0; }}
    .toc li {{ margin: 4px 0; }}
  </style>
</head>
<body>
{html_body}
</body>
</html>"""


def generate_pdf(output: Path | None = None) -> Path:
    target = output or PDF_FILE
    md_content = MD_FILE.read_text(encoding="utf-8")
    html = build_html(md_content)
    temp_pdf = target.with_suffix(".tmp.pdf")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="networkidle")
        page.pdf(
            path=str(temp_pdf),
            format="A4",
            print_background=True,
            margin={"top": "18mm", "bottom": "20mm", "left": "16mm", "right": "16mm"},
            display_header_footer=True,
            header_template="<div></div>",
            footer_template=(
                '<div style="width:100%;font-size:8pt;color:#666;text-align:center;'
                'padding:0 16mm;">F2 Platform Design Document — Page '
                '<span class="pageNumber"></span> of <span class="totalPages"></span></div>'
            ),
        )
        browser.close()

    try:
        temp_pdf.replace(target)
    except PermissionError:
        fallback = target.with_name(f"{target.stem}-new{target.suffix}")
        temp_pdf.replace(fallback)
        print(f"Warning: could not overwrite {target} (file may be open). Wrote to {fallback}")
        return fallback
    return target


if __name__ == "__main__":
    result = generate_pdf(UPDATED_PDF_FILE)
    print(f"Generated: {result} ({result.stat().st_size:,} bytes)")
