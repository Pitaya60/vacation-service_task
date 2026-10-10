"""Добавляет в DEVLOG.md строку с РЕАЛЬНЫМ временем вашего компьютера.

Использование:
    python scripts/log.py "что сделал и почему"             # только запись в DEVLOG.md
    python scripts/log.py --commit "что сделал и почему"    # запись + git add -A + git commit с тем же текстом

Время берётся из часов компьютера в момент запуска, подставить его задним числом нельзя.
"""
import pathlib, subprocess, sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
args = sys.argv[1:]
commit = "--commit" in args
text = " ".join(a for a in args if a != "--commit").strip()
if not text:
    sys.exit(__doc__)

line = f"- **{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')}** — {text}\n"
with open(ROOT / "DEVLOG.md", "a", encoding="utf-8") as f:
    f.write(line)
print("ok:", line.strip())

if commit:
    for cmd in (["git", "add", "-A"], ["git", "commit", "-m", text]):
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"git: {' '.join(cmd)} не выполнено:\n{r.stdout}{r.stderr}")
    print("коммит создан:", text)
