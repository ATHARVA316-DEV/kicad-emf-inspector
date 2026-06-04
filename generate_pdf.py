import markdown
import sys
import re
import os
import base64

def render_paper(md_path="paper.md", html_path="paper.html"):
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    # ── Extract metadata from YAML frontmatter ──────────────────────────
    title = "EMF Inspector"
    authors = "Atharva M"
    affiliation = ""
    orcid = ""
    date_str = ""

    if md_text.startswith("---"):
        parts = md_text.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            md_text = parts[2]
            t_match = re.search(r"title:\s*'(.*?)'", frontmatter)
            if t_match:
                title = t_match.group(1)
            a_match = re.search(r"name:\s*(.*)", frontmatter)
            if a_match:
                authors = a_match.group(1).strip()
            o_match = re.search(r"orcid:\s*(.*)", frontmatter)
            if o_match:
                orcid = o_match.group(1).strip()
            aff_match = re.search(r"affiliations:\s*\n\s*-\s*name:\s*(.*)", frontmatter)
            if aff_match:
                affiliation = aff_match.group(1).strip()
            d_match = re.search(r"date:\s*(.*)", frontmatter)
            if d_match:
                date_str = d_match.group(1).strip()

    # ── Process citations: [@ref] → superscript [1] ─────────────────────
    citations = []

    def cite_repl(match):
        ref_key = match.group(1)
        if ref_key not in citations:
            citations.append(ref_key)
        idx = citations.index(ref_key) + 1
        return f'<sup>[{idx}]</sup>'

    md_text = re.sub(r"\[@(.*?)\]", cite_repl, md_text)

    # ── Number sections: # Heading → 1. Heading ─────────────────────────
    section_counter = [0]

    def number_h1(match):
        heading_text = match.group(1).strip()
        if heading_text.lower() == "references":
            return f"# References"
        section_counter[0] += 1
        return f"# {section_counter[0]}. {heading_text}"

    md_text = re.sub(r"^#\s+(.+)$", number_h1, md_text, flags=re.MULTILINE)

    # ── Embed screenshot as base64 so PDF is self-contained ──────────────
    screenshot_path = os.path.join(os.path.dirname(md_path) or ".", "screenshot.png")
    if os.path.exists(screenshot_path):
        with open(screenshot_path, "rb") as img_f:
            img_b64 = base64.b64encode(img_f.read()).decode("utf-8")
        # Replace markdown image with HTML figure + caption
        def replace_img(match):
            alt_text = match.group(1)
            return (
                f'<figure>'
                f'<img src="data:image/png;base64,{img_b64}" alt="{alt_text}">'
                f'<figcaption><strong>Figure 1.</strong> {alt_text}</figcaption>'
                f'</figure>'
            )
        md_text = re.sub(r"!\[(.*?)\]\(screenshot\.png\)", replace_img, md_text)

    # ── Convert markdown to HTML ─────────────────────────────────────────
    try:
        html_content = markdown.markdown(md_text, extensions=['mdx_math', 'tables'])
    except Exception:
        html_content = markdown.markdown(md_text, extensions=['tables'])

    # ── Build formatted reference list from paper.bib ────────────────────
    try:
        with open("paper.bib", "r", encoding="utf-8") as f:
            bib_text = f.read()

        bib_dict = {}
        entries = re.finditer(r"@\w+\{(.*?),\s*(.*?)\n\}", bib_text, re.DOTALL)
        for entry in entries:
            key = entry.group(1).strip()
            content = entry.group(2)

            author_m = re.search(r"author\s*=\s*[{](.*?)[}]", content, re.IGNORECASE | re.DOTALL)
            title_m = re.search(r"title\s*=\s*[{](.*?)[}]", content, re.IGNORECASE | re.DOTALL)
            year_m = re.search(r"year\s*=\s*[{](.*?)[}]", content, re.IGNORECASE)
            journal_m = re.search(r"journal\s*=\s*[{](.*?)[}]", content, re.IGNORECASE)
            publisher_m = re.search(r"publisher\s*=\s*[{](.*?)[}]", content, re.IGNORECASE)
            doi_m = re.search(r"doi\s*=\s*[{](.*?)[}]", content, re.IGNORECASE)
            volume_m = re.search(r"volume\s*=\s*[{](.*?)[}]", content, re.IGNORECASE)
            pages_m = re.search(r"pages\s*=\s*[{](.*?)[}]", content, re.IGNORECASE)
            url_m = re.search(r"howpublished\s*=\s*[{]\\url[{](.*?)[}][}]", content, re.IGNORECASE)

            author = author_m.group(1).replace('\n', ' ').strip() if author_m else "Unknown"
            t = title_m.group(1).replace('\n', ' ').replace('{', '').replace('}', '').strip() if title_m else "Untitled"
            year = year_m.group(1) if year_m else ""

            parts = []
            parts.append(f'{author},')
            parts.append(f'"{t},"')
            if journal_m:
                j = journal_m.group(1).replace('{', '').replace('}', '')
                parts.append(f'<em>{j}</em>,')
            if volume_m:
                vol = volume_m.group(1)
                pg = pages_m.group(1).replace('--', '–') if pages_m else ""
                if pg:
                    parts.append(f'vol. {vol}, pp. {pg},')
                else:
                    parts.append(f'vol. {vol},')
            if publisher_m and not journal_m:
                parts.append(f'{publisher_m.group(1)},')
            parts.append(f'{year}.')
            if doi_m:
                parts.append(f'doi: <a href="https://doi.org/{doi_m.group(1)}">{doi_m.group(1)}</a>.')
            elif url_m:
                parts.append(f'[Online]. Available: <a href="{url_m.group(1)}">{url_m.group(1)}</a>.')

            bib_dict[key] = " ".join(parts)

        ref_html = '<ol class="references">'
        for key in citations:
            ref_text = bib_dict.get(key, f"[{key}] — reference not found in paper.bib")
            ref_html += f"<li>{ref_text}</li>"
        ref_html += "</ol>"

        html_content = html_content.replace("<h1>References</h1>", f"<h1>References</h1>\n{ref_html}")

    except Exception as e:
        print("Could not process bibliography:", e)

    # ── Author block HTML ────────────────────────────────────────────────
    orcid_html = ""
    if orcid:
        orcid_html = (
            f'<div class="orcid">'
            f'<img src="https://orcid.org/sites/default/files/images/orcid_16x16.png" '
            f'alt="ORCID" style="width:14px; height:14px; vertical-align:middle; margin-right:4px;">'
            f'<a href="https://orcid.org/{orcid}">{orcid}</a>'
            f'</div>'
        )

    author_block = f"""
    <div class="author-block">
        <div class="author-name">{authors}</div>
        <div class="author-affiliation">{affiliation}</div>
        {orcid_html}
        <div class="paper-date">{date_str}</div>
    </div>
    """

    # ── Full HTML with professional academic CSS ─────────────────────────
    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <script>
      MathJax = {{ tex: {{ inlineMath: [['$', '$']], displayMath: [['$$', '$$']], tags: 'ams' }} }};
    </script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        /* ── Reset & Base ──────────────────────────────────────── */
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

        @page {{
            size: A4;
            margin: 22mm 18mm 25mm 18mm;
        }}

        body {{
            font-family: "Times New Roman", "Nimbus Roman No9 L", Times, serif;
            font-size: 10pt;
            line-height: 1.45;
            color: #1a1a1a;
            text-align: justify;
            text-justify: inter-word;
            -webkit-hyphens: auto;
            hyphens: auto;
            max-width: 190mm;
            margin: 0 auto;
            padding: 15mm 0;
        }}

        @media screen {{
            body {{
                max-width: 800px;
                padding: 30px 25px;
                background: #f5f5f0;
            }}
            body > * {{
                background: white;
            }}
        }}

        /* ── Title ─────────────────────────────────────────────── */
        .paper-title {{
            font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
            font-size: 18pt;
            font-weight: 700;
            text-align: center;
            line-height: 1.25;
            margin: 0 0 12pt 0;
            color: #111;
            letter-spacing: -0.3px;
        }}

        /* ── Author Block ──────────────────────────────────────── */
        .author-block {{
            text-align: center;
            margin-bottom: 18pt;
            padding-bottom: 12pt;
            border-bottom: 0.5pt solid #ccc;
        }}
        .author-name {{
            font-size: 12pt;
            font-weight: 600;
            font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
            margin-bottom: 3pt;
        }}
        .author-affiliation {{
            font-size: 9pt;
            color: #444;
            font-style: italic;
            margin-bottom: 2pt;
        }}
        .orcid {{
            font-size: 8.5pt;
            color: #666;
            margin-bottom: 2pt;
        }}
        .orcid a {{
            color: #a6ce39;
            text-decoration: none;
        }}
        .paper-date {{
            font-size: 8.5pt;
            color: #888;
            margin-top: 4pt;
        }}

        /* ── Abstract ──────────────────────────────────────────── */
        .content > p:first-of-type {{
            /* Style the first paragraph (abstract intro) slightly */
        }}

        /* ── Section Headings ──────────────────────────────────── */
        h1 {{
            font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
            font-size: 12pt;
            font-weight: 700;
            color: #1a1a1a;
            margin: 18pt 0 6pt 0;
            padding-bottom: 3pt;
            border-bottom: 0.4pt solid #ddd;
            text-align: left;
        }}

        h2 {{
            font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
            font-size: 10.5pt;
            font-weight: 600;
            color: #333;
            margin: 12pt 0 4pt 0;
            text-align: left;
        }}

        h3 {{
            font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
            font-size: 10pt;
            font-weight: 600;
            font-style: italic;
            color: #444;
            margin: 10pt 0 3pt 0;
            text-align: left;
        }}

        /* ── Paragraphs ───────────────────────────────────────── */
        p {{
            margin: 0 0 6pt 0;
            text-indent: 1.5em;
            orphans: 3;
            widows: 3;
        }}

        /* First paragraph after heading: no indent */
        h1 + p, h2 + p, h3 + p,
        figure + p,
        .author-block + .content > p:first-child {{
            text-indent: 0;
        }}

        /* ── Code / monospace ──────────────────────────────────── */
        code {{
            font-family: "Courier New", Courier, monospace;
            font-size: 9pt;
            background: #f4f4f4;
            padding: 1px 3px;
            border-radius: 2px;
        }}

        /* ── Figures ───────────────────────────────────────────── */
        figure {{
            margin: 14pt 0;
            text-align: center;
            page-break-inside: avoid;
        }}
        figure img {{
            max-width: 100%;
            height: auto;
            border: 0.3pt solid #ddd;
            border-radius: 2pt;
        }}
        figcaption {{
            font-size: 9pt;
            color: #333;
            margin-top: 6pt;
            text-align: center;
            font-style: normal;
            text-indent: 0;
        }}
        figcaption strong {{
            font-weight: 700;
        }}

        /* ── Tables ────────────────────────────────────────────── */
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 12pt 0;
            font-size: 8.5pt;
            page-break-inside: avoid;
        }}
        thead th {{
            background: #2c3e50;
            color: white;
            font-weight: 600;
            font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
            padding: 6pt 8pt;
            text-align: center;
            border: none;
        }}
        tbody td {{
            padding: 5pt 8pt;
            text-align: center;
            border-bottom: 0.3pt solid #ddd;
            text-indent: 0;
        }}
        tbody tr:nth-child(even) {{
            background: #f8f9fa;
        }}
        tbody tr:last-child {{
            font-weight: 600;
            background: #eef5db;
        }}

        /* ── Equations ─────────────────────────────────────────── */
        .MathJax {{
            font-size: 105% !important;
        }}
        mjx-container[jax="CHTML"][display="true"] {{
            margin: 10pt 0 !important;
        }}

        /* ── Reference List ────────────────────────────────────── */
        ol.references {{
            padding-left: 2em;
            margin-top: 8pt;
            font-size: 8.5pt;
            line-height: 1.4;
            counter-reset: list-counter;
        }}
        ol.references li {{
            margin-bottom: 5pt;
            padding-left: 4pt;
            text-indent: 0;
        }}
        ol.references a {{
            color: #2563eb;
            text-decoration: none;
            word-break: break-all;
        }}

        /* ── Superscript Citations ─────────────────────────────── */
        sup {{
            font-size: 7.5pt;
            line-height: 0;
            color: #2563eb;
            font-weight: 600;
        }}

        /* ── Links ─────────────────────────────────────────────── */
        a {{
            color: #2563eb;
            text-decoration: none;
        }}

        /* ── Print / PDF specifics ─────────────────────────────── */
        @media print {{
            body {{
                max-width: 100%;
                padding: 0;
                background: white;
            }}
            h1 {{
                page-break-after: avoid;
            }}
            figure, table {{
                page-break-inside: avoid;
            }}
        }}
    </style>
</head>
<body>
    <div class="paper-title">{title}</div>
    {author_block}
    <div class="content">
        {html_content}
    </div>
</body>
</html>
"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_template)

    print(f"Generated {html_path} successfully!")

if __name__ == "__main__":
    render_paper()
