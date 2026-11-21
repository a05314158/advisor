from pathlib import Path
html = Path("wallet.html").read_text(encoding="utf-8")
i = html.find('id="cardsPanel"')
j = html.find('id="historyPanel"')
Path("_cards_chunk.txt").write_text(html[i - 80:j], encoding="utf-8")
k = html.find('class="wallet-nav"')
Path("_nav_chunk.txt").write_text(html[k:k + 2500], encoding="utf-8")
w = Path("welcome.html").read_text(encoding="utf-8")
lines = w.splitlines()
print("wallet", len(html), "lines", html.count("\n") + 1)
print("welcome", len(w), "lines", len(lines))
for n, line in enumerate(lines, 1):
    print(n, len(line))
