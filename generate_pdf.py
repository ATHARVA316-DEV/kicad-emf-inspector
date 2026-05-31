import markdown
import sys
import re

def render_paper(md_path="paper.md", html_path="paper.html"):
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()
        
    # Extract Title and Authors from YAML
    title = "EMF Inspector"
    authors = "Atharva M"
    if md_text.startswith("---"):
        parts = md_text.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            md_text = parts[2]
            t_match = re.search(r"title:\s*'(.*?)'", frontmatter)
            if t_match: title = t_match.group(1)

    # 1. Process citations in the text: [@ref] -> [1]
    # We will build a list of references in the order they appear
    citations = []
    
    def cite_repl(match):
        ref_key = match.group(1)
        if ref_key not in citations:
            citations.append(ref_key)
        idx = citations.index(ref_key) + 1
        return f"[{idx}]"
        
    # Find all [@...]
    md_text = re.sub(r"\[@(.*?)\]", cite_repl, md_text)

    # 2. Convert to HTML
    try:
        html_content = markdown.markdown(md_text, extensions=['mdx_math', 'tables'])
    except Exception:
        html_content = markdown.markdown(md_text, extensions=['tables'])

    # 3. Read paper.bib and extract formatted references
    try:
        with open("paper.bib", "r", encoding="utf-8") as f:
            bib_text = f.read()
            
        bib_dict = {}
        # Super simple regex to grab bibtex entries
        entries = re.finditer(r"@\w+\{(.*?),\s*(.*?)\n\}", bib_text, re.DOTALL)
        for entry in entries:
            key = entry.group(1).strip()
            content = entry.group(2)
            
            # Extract basic fields
            author_m = re.search(r"author\s*=\s*[{](.*?)[}]", content, re.IGNORECASE | re.DOTALL)
            title_m = re.search(r"title\s*=\s*[{](.*?)[}]", content, re.IGNORECASE | re.DOTALL)
            year_m = re.search(r"year\s*=\s*[{](.*?)[}]", content, re.IGNORECASE)
            journal_m = re.search(r"journal\s*=\s*[{](.*?)[}]", content, re.IGNORECASE)
            publisher_m = re.search(r"publisher\s*=\s*[{](.*?)[}]", content, re.IGNORECASE)
            
            author = author_m.group(1).replace('\n', ' ') if author_m else "Unknown Author"
            t = title_m.group(1).replace('\n', ' ') if title_m else "Unknown Title"
            year = year_m.group(1) if year_m else ""
            
            source = ""
            if journal_m: source = f"<em>{journal_m.group(1)}</em>"
            elif publisher_m: source = publisher_m.group(1)
            
            # format it as a string
            bib_dict[key] = f"{author} ({year}). {t}. {source}."
            
        # Append references to the HTML
        ref_html = "<ol>"
        for key in citations:
            ref_text = bib_dict.get(key, f"Reference {key} not found")
            ref_html += f"<li>{ref_text}</li>"
        ref_html += "</ol>"
        
        # Insert ref_html right after the <h1>References</h1> or similar
        html_content = html_content.replace("<h1>References</h1>", f"<h1>References</h1>\n{ref_html}")
        
    except Exception as e:
        print("Could not process bibliography:", e)

    # 4. Generate final HTML with CSS
    html_template = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <script>
      MathJax = {{ tex: {{ inlineMath: [['$', '$']], displayMath: [['$$', '$$']], tags: 'ams' }} }};
    </script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        body {{
            font-family: "Times New Roman", Times, serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 40px auto;
            color: #111;
            padding: 0 20px;
            text-align: justify;
        }}
        h1, h2, h3 {{ font-family: Arial, Helvetica, sans-serif; color: #222; }}
        h1 {{ text-align: center; font-size: 24px; margin-bottom: 5px; }}
        .authors {{ text-align: center; font-style: italic; margin-bottom: 30px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; font-size: 0.9em; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
        th {{ background-color: #f4f4f4; }}
        img {{ max-width: 100%; height: auto; display: block; margin: 20px auto; }}
        ol {{ padding-left: 20px; }}
        li {{ margin-bottom: 8px; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <div class="authors">{authors}</div>
    {html_content}
</body>
</html>
"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_template)
    
    print(f"Generated {html_path} successfully with bibliography!")

if __name__ == "__main__":
    render_paper()
