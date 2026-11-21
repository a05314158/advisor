from pathlib import Path
lines = Path("welcome.html").read_text(encoding="utf-8").splitlines()
for n in range(49, 74):
    text = lines[n]
    if len(text) > 300:
        text = text[:180] + " ... " + text[-80:]
    print(f"{n+1}|{text}")
print("---planner---")
print(Path("static/planner.css").read_text(encoding="utf-8")[:800])
