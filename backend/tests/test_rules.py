from datetime import date as D
from app import rules
from app.rules import accrued, validate_parts, check_balance

P = lambda a, b: (D.fromisoformat(a), D.fromisoformat(b))


def test_accrual_year():
    assert accrued(D(2025, 1, 1), D(2026, 1, 1)) == 28

def test_accrual_before_hire_is_zero():
    assert accrued(D(2025, 1, 10), D(2025, 1, 1)) == 0

def test_accrual_hire_date_change():
    assert accrued(D(2025, 6, 1), D(2026, 1, 1)) < accrued(D(2025, 1, 1), D(2026, 1, 1))

def test_no_14_day_part():
    assert validate_parts([P("2026-07-01", "2026-07-07"), P("2026-08-01", "2026-08-07")]) == "В заявке нет части от 14 дней."

def test_part_shorter_than_5():
    assert "не короче 5" in validate_parts([P("2026-07-01", "2026-07-14"), P("2026-08-01", "2026-08-03")])

def test_more_than_3_parts():
    assert "Не более 3" in validate_parts([P(f"2026-0{i}-01", f"2026-0{i}-14") for i in (1, 2, 3, 4)])

def test_overlap():
    assert "пересекаются" in validate_parts([P("2026-07-01", "2026-07-14"), P("2026-07-10", "2026-07-20")])

def test_past_start_rejected():
    assert "задним числом" in validate_parts([P("2026-07-01", "2026-07-14")], today=D(2026, 10, 10))

def test_valid_14_plus_7():
    assert validate_parts([P("2026-07-01", "2026-07-14"), P("2026-08-01", "2026-08-07")]) is None

def test_balance_exceeded():
    assert "накоплено" in check_balance(D(2026, 1, 1), [], [P("2026-02-01", "2026-02-14")])

def test_balance_ok():
    assert check_balance(D(2025, 1, 1), [], [P("2026-02-01", "2026-02-14")]) is None

def test_balance_counts_existing():
    assert "накоплено" in check_balance(D(2025, 6, 1), [P("2026-01-05", "2026-01-25")], [P("2026-02-01", "2026-02-14")])


def test_year_limit_counts_parts_by_start_year():
    from datetime import date as d
    ex = [(d(2027, 2, 1), d(2027, 2, 14)), (d(2027, 3, 1), d(2027, 3, 5)), (d(2027, 4, 1), d(2027, 4, 5))]
    assert rules.check_year_limit(ex, [(d(2027, 5, 3), d(2027, 5, 16))]) is None       # четвёртая часть разрешена
    msg = rules.check_year_limit(ex + [(d(2027, 5, 3), d(2027, 5, 16))], [(d(2027, 6, 1), d(2027, 6, 14))])
    assert msg and "2027" in msg and "больше 4" in msg                                  # пятая нельзя
    assert rules.check_year_limit(ex * 2, [(d(2028, 1, 10), d(2028, 1, 23))]) is None   # другой год считается отдельно


def test_review_balance_lists_uncovered_parts():
    from datetime import date as d
    parts = [(d(2026, 12, 1), d(2026, 12, 28))]
    assert rules.review_balance(d(2025, 3, 1), parts) == []
    bad = rules.review_balance(d(2026, 6, 1), parts)
    assert bad and bad[0][1] == 14 and bad[0][2] == 28


def test_free_days_takes_future_parts_into_account():
    hire = D(2025, 3, 1)                       # к 2026-10-10 накоплено 45
    on = D(2026, 10, 10)
    assert rules.free_days(hire, [], on) == 45
    assert rules.free_days(hire, [(D(2026, 10, 20), D(2026, 11, 2))], on) == 31
    # будущая длинная часть, которой «впритык» хватает накопления, ограничивает свободные дни сильнее, чем остаток на сегодня
    tight = (D(2027, 6, 1), D(2027, 8, 1))  # 62 дня; к 2027-06-01 накоплено 63
    assert rules.accrued(hire, tight[0]) == 63 and rules.plen(tight) == 62
    assert rules.free_days(hire, [tight], on) == 1
    assert rules.free_days(D(2026, 10, 1), [], on) == 0
