from datetime import date as D
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
