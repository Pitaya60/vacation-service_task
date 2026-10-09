"""Чистые правила предметной области (описаны в README). Без обращений к БД."""
from datetime import date

ANNUAL = 28
Part = tuple[date, date]  # (начало, конец) включительно


def accrued(hire: date, on: date) -> int:
    """Накоплено на дату: 28 * отработанные_дни / 365, вниз до целого."""
    return max(0, (ANNUAL * (on - hire).days) // 365)


def plen(p: Part) -> int:
    return (p[1] - p[0]).days + 1


def validate_parts(parts: list[Part], today: date | None = None) -> str | None:
    if not parts:
        return "В заявке нет ни одной части."
    if len(parts) > 3:
        return "Не более 3 частей в одной заявке."
    if any(plen(p) < 1 for p in parts):
        return "Дата окончания раньше даты начала."
    if today and any(p[0] < today for p in parts):
        return "Нельзя оформить отпуск задним числом."
    s = sorted(parts)
    if any(s[i][0] <= s[i - 1][1] for i in range(1, len(s))):
        return "Части отпуска пересекаются."
    if not any(plen(p) >= 14 for p in parts):
        return "В заявке нет части от 14 дней."
    if any(plen(p) < 5 for p in parts):
        return "Каждая часть должна быть не короче 5 дней."
    return None


def check_balance(hire: date, existing: list[Part], added: list[Part]) -> str | None:
    """Нарастающий итог дней по хронологии не должен превышать накопленное к началу каждой части."""
    cum = 0
    for p in sorted(existing + added):
        cum += plen(p)
        a = accrued(hire, p[0])
        if cum > a:
            return f"К {p[0].isoformat()} накоплено {a} дн., а с этой заявкой потребуется {cum} дн."
    return None
