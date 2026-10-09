"""Добавляет в DEVLOG.md строку с РЕАЛЬНЫМ временем вашего компьютера.
Использование: python scripts/log.py "что сделал и почему"
"""
import pathlib, sys
from datetime import datetime

line = f"- **{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')}** — {' '.join(sys.argv[1:])}\n"
with open(pathlib.Path(__file__).resolve().parents[1] / "DEVLOG.md", "a", encoding="utf-8") as f:
    f.write(line)
print("ok:", line.strip())
