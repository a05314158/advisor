from pathlib import Path
w = Path("welcome.html").read_text(encoding="utf-8").splitlines()
line = w[61]
print(line[:400])
print("---tail---")
print(line[-200:])
print("start count", line.count("<svg"), line.count("data:image"))
html = Path("wallet.html").read_text(encoding="utf-8")
# find script function names roughly
print("themeToggle count", html.count("themeToggle"))
print("renderPocket", html.count("renderPocket"))
print("savedList", html.count("savedList"))
