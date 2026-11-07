"""Build report.pdf from report.md: pandoc to HTML, then headless Chromium (Node Playwright) to PDF.

    python3 reports/2026-11-07-best-wind/build_pdf.py
"""
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent

CSS = """
@page { size: Letter; margin: 18mm 16mm 18mm 16mm; }
body { font-family: Georgia, 'Times New Roman', serif; font-size: 10.5pt; line-height: 1.42; color: #1f1f1d; max-width: none; }
header#title-block-header { text-align: center; margin-bottom: 14pt; }
h1.title { font-size: 18pt; margin: 0 0 6pt; color: #14284b; }
p.subtitle { font-size: 12pt; margin: 0 0 6pt; color: #5f5e5a; }
p.author, p.date { margin: 2pt 0; font-size: 10pt; color: #5f5e5a; }
h2 { font-size: 13.5pt; color: #14284b; border-bottom: 1px solid #c9c4b5; padding-bottom: 2pt; margin-top: 16pt; break-after: avoid; }
h3 { font-size: 11.5pt; color: #6b1d1d; margin-top: 12pt; break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; font-size: 8.4pt; break-inside: avoid; }
th, td { border-bottom: 1px solid #e2ded3; padding: 3pt 5pt; text-align: left; vertical-align: top; }
th { background: #f4f1e8; color: #14284b; }
figure { margin: 10pt 0; text-align: center; break-inside: avoid; }
figure img { max-width: 100%; max-height: 92mm; }
figcaption { font-size: 9pt; color: #5f5e5a; text-align: left; margin-top: 4pt; }
code { font-size: 8.6pt; }
hr { border: 0; border-top: 1px solid #c9c4b5; margin: 12pt 0; }
"""


def main():
    css = HERE / "report.css"
    css.write_text(CSS)
    html = HERE / "report.html"
    subprocess.run(["pandoc", "report.md", "-s", "--from", "markdown+implicit_figures",
                    "--css", "report.css", "--embed-resources", "--metadata", "lang=en",
                    "-o", str(html)], cwd=HERE, check=True)
    js = """
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const pg = await b.newPage();
  await pg.goto(process.argv[2]);
  await pg.pdf({ path: process.argv[3], format: 'Letter', printBackground: true,
    displayHeaderFooter: true, headerTemplate: '<span></span>',
    footerTemplate: "<div style='font-size:8px;width:100%;text-align:center;color:#888'>Best Wind research report &middot; <span class='pageNumber'></span> / <span class='totalPages'></span></div>",
    margin: { top: '16mm', bottom: '16mm', left: '15mm', right: '15mm' } });
  await b.close();
})();
"""
    # Playwright ships with the session image for Node; run it from a temp script.
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(js)
    try:
        subprocess.run(["node", f.name, html.as_uri(), str(HERE / "report.pdf")], check=True)
    finally:
        Path(f.name).unlink()
    html.unlink()
    css.unlink()
    print(HERE / "report.pdf")


if __name__ == "__main__":
    main()
