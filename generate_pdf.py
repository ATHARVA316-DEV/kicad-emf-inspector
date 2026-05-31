import markdown
import sys
import re

def render_paper(md_path="paper.md", html_path="paper.html"):
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    # The markdown file contains YAML frontmatter and Citations like [@ott2009]
    # Let's clean up the citations to look like [1], [2] etc for the printout.
    
    # Strip YAML frontmatter for the HTML version, but extract title/authors
    title = "EMF Inspector"
    authors = "Atharva M"
    
    if md_text.startswith("---"):
        parts = md_text.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            md_text = parts[2]
            
            # extract title
            t_match = re.search(r"title:\s*'(.*?)'", frontmatter)
            if t_match: title = t_match.group(1)

    # Convert to HTML (including math extension if installed)
    try:
        html_content = markdown.markdown(md_text, extensions=['mdx_math', 'tables'])
    except Exception:
        # Fallback if mdx_math fails
        html_content = markdown.markdown(md_text, extensions=['tables'])

    html_template = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <!-- MathJax for rendering LaTeX equations -->
    <script>
      MathJax = {{
        tex: {{
          inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
          displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
          tags: 'ams'
        }}
      }};
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
        h1, h2, h3 {{
            font-family: Arial, Helvetica, sans-serif;
            color: #222;
        }}
        h1 {{ text-align: center; font-size: 24px; margin-bottom: 5px; }}
        .authors {{ text-align: center; font-style: italic; margin-bottom: 30px; }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 20px 0;
            font-size: 0.9em;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 8px;
            text-align: center;
        }}
        th {{ background-color: #f4f4f4; }}
        code {{
            background-color: #f4f4f4;
            padding: 2px 4px;
            border-radius: 4px;
            font-family: monospace;
            font-size: 0.9em;
        }}
        img {{
            max-width: 100%;
            height: auto;
            display: block;
            margin: 20px auto;
        }}
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
    
    print(f"Generated {html_path} successfully!")

if __name__ == "__main__":
    render_paper()
