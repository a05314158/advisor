from pathlib import Path
html = Path("wallet.html").read_text(encoding="utf-8")
start = html.find("function applyCarouselTransforms()")
end = html.find("function cubicBezier")
Path("_apply.js").write_text(html[start:end], encoding="utf-8")
print(end-start)
