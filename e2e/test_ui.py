"""Сквозные проверки интерфейса в настоящем браузере (Chromium через Playwright).

Нужны запущенные backend и собранный frontend (см. e2e/README.md). Тесты не требуют чистой БД:
даты выбираются случайно в далёком будущем, дата выхода Ивана после проверки возвращается.
"""
import os, random, re

import pytest

sync_api = pytest.importorskip("playwright.sync_api", reason="pip install playwright && playwright install chromium")
BASE = os.environ.get("E2E_URL", "http://localhost:4173")
SHOTS = os.environ.get("E2E_SHOTS")  # папка для скриншотов, если нужна


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def open_as(browser):
    pages = []

    def go(name: str, width=1280, height=900):
        pg = browser.new_context(viewport={"width": width, "height": height}).new_page()
        pg.goto(BASE)
        pg.get_by_role("button", name=re.compile(f"^{name}")).click()
        pg.wait_for_selector(".top")
        pages.append(pg)
        return pg
    yield go
    for pg in pages:
        pg.context.close()


def shot(pg, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        pg.screenshot(path=os.path.join(SHOTS, name + ".png"), full_page=True)


def fill_request(pg, a, b):
    pg.fill("#s0", a)
    pg.fill("#e0", b)
    pg.get_by_role("button", name="Отправить на согласование").click()


def test_rule_error_shows_inside_the_form(open_as):
    iv = open_as("Иван")
    iv.wait_for_selector(".hero")
    fill_request(iv, "2041-03-01", "2041-03-03")
    iv.wait_for_selector(".alert")
    assert iv.inner_text(".alert") == "В заявке нет части от 14 дней."
    shot(iv, "employee")


def test_request_reaches_manager_and_rejection_reaches_employee(open_as):
    year = random.randint(2042, 2090)
    iv, bo = open_as("Иван"), open_as("Игорь")
    iv.wait_for_selector(".hero")
    bo.wait_for_selector(".tab")
    before = int(bo.locator(".tabs .count").inner_text()) if bo.locator(".tabs .count").count() else 0
    items_before = iv.locator(".list .item").count()
    fill_request(iv, f"{year}-05-03", f"{year}-05-16")
    iv.wait_for_selector(".toast.ok")
    iv.wait_for_function("(n) => document.querySelectorAll('.list .item').length > n", arg=items_before)   # список обновился
    # менеджер видит новую заявку без перезагрузки страницы (SSE)
    bo.wait_for_function("(n) => { const c = document.querySelector('.tabs .count'); return c && Number(c.innerText) > n }", arg=before, timeout=10000)
    vid = re.search(r"заявка №(\d+)", iv.locator(".list .item").first.inner_text()).group(1)
    card = bo.locator(".item", has_text=re.compile(rf"заявка №{vid}(?!\d)"))
    card.get_by_role("button", name="Отклонить").click()
    assert card.get_by_role("button", name="Отклонить заявку").is_disabled()          # без причины нельзя
    card.locator("textarea").fill("В эти даты релиз")
    card.get_by_role("button", name="Отклонить заявку").click()
    bo.wait_for_selector(".toast.ok")
    shot(bo, "manager")
    mine = iv.locator(".item", has_text=re.compile(rf"заявка №{vid}(?!\d)"))
    mine.locator(".why").wait_for(timeout=10000)
    assert "В эти даты релиз" in mine.locator(".why").inner_text()


def test_hr_changes_hire_date_and_accrual_recalculates(open_as):
    hr = open_as("Анна")
    hr.wait_for_selector("table")
    row = lambda: hr.locator("tbody tr", has_text="Иван")
    before = int(row().locator("td.num").nth(0).inner_text())
    original = row().locator("input").input_value()
    row().locator("input").fill("2023-03-01")
    row().get_by_role("button", name="Сохранить").click()
    hr.wait_for_selector(".toast.ok")
    hr.wait_for_function("(n) => [...document.querySelectorAll('tbody tr')].find(r => r.innerText.includes('Иван')).querySelectorAll('td.num')[0].innerText != n", arg=str(before))
    assert int(row().locator("td.num").nth(0).inner_text()) > before
    shot(hr, "hr")
    hr.get_by_role("button", name="Календарь компании").click()
    hr.wait_for_selector(".cal-head")
    shot(hr, "hr-calendar")
    hr.get_by_role("button", name="Сотрудники и остатки").click()
    row().locator("input").fill(original)
    row().get_by_role("button", name="Сохранить").click()
    hr.wait_for_selector(".toast.ok")


def test_bell_counts_unread_and_clears_after_opening(open_as):
    year = random.randint(2042, 2090)
    iv, bo = open_as("Иван"), open_as("Игорь")
    iv.wait_for_selector(".hero")
    fill_request(iv, f"{year}-08-02", f"{year}-08-15")
    iv.wait_for_selector(".toast.ok")
    bell = bo.locator("button.bell")
    bell.locator(".bell-count").wait_for(timeout=10000)
    assert "непрочитанных" in bell.get_attribute("aria-label")
    bell.click()
    assert bo.locator(".pop li.fresh").count() >= 1
    bell.click()
    bo.wait_for_function("() => !document.querySelector('.bell-count')", timeout=10000)


def test_mobile_layout_has_no_horizontal_scroll(open_as):
    iv = open_as("Иван", 390, 844)
    iv.wait_for_selector(".hero")
    assert not iv.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    shot(iv, "mobile")
