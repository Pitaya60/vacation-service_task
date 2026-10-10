"""Чистые правила предметной области (описаны в README). Без обращений к БД."""
from datetime import date

ANNUAL = 28
MAX_PARTS_PER_YEAR = 4  # частей отпуска в календарном году (по дате начала), считаются заявки в статусах «на рассмотрении» и «согласован»
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


def check_year_limit(existing: list[Part], added: list[Part], limit: int = MAX_PARTS_PER_YEAR) -> str | None:
    """Не более `limit` частей отпуска в календарном году (год определяется по дате начала части)."""
    by_year: dict[int, int] = {}
    for p in existing + added:
        by_year[p[0].year] = by_year.get(p[0].year, 0) + 1
    for year in sorted({p[0].year for p in added}):
        if by_year[year] > limit:
            return f"В {year} году уже {by_year[year] - len([p for p in added if p[0].year == year])} частей отпуска, а с этой заявкой будет {by_year[year]}: больше {limit} частей в год нельзя."
    return None


def review_balance(hire: date, parts: list[Part]) -> list[tuple[Part, int, int]]:
    """Части, которые после смены даты выхода не покрываются накоплением: (часть, накоплено, нужно нарастающим итогом)."""
    out, cum = [], 0
    for p in sorted(parts):
        cum += plen(p)
        a = accrued(hire, p[0])
        if cum > a:
            out.append((p, a, cum))
    return out
