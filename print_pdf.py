from playwright.sync_api import sync_playwright
import os

def generate_pdf():
    html_path = os.path.abspath("paper.html")
    url = f"file:///{html_path.replace(chr(92), '/')}"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        
        # Give MathJax an extra 3 seconds to render just in case
        page.wait_for_timeout(3000)
        
        page.pdf(
            path="EMF_Inspector_Paper_Final.pdf",
            format="A4",
            print_background=True,
            margin={"top": "20mm", "bottom": "20mm", "left": "20mm", "right": "20mm"}
        )
        browser.close()
        
    print("PDF generated successfully at EMF_Inspector_Paper.pdf")

if __name__ == "__main__":
    generate_pdf()
