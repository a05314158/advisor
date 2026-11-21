"""Exercise the visible wallet in Chromium; always start a private loopback server and DB."""
import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
WIDTHS = (320, 360, 390, 430, 1280)
REC = '**/api/recommendations'


@contextmanager
def isolated_server():
    import uvicorn
    sys.path.insert(0, str(ROOT))
    from catalog import SEED, import_catalog
    with tempfile.TemporaryDirectory(prefix='advisor-smoke-') as tmp, socket.socket() as sock:
        db = str(Path(tmp) / 'wallet.sqlite3')
        # Keep the real seed rates, caps, thresholds and ordering valid on future CI dates.
        import_catalog(db, [dict(row, validFrom='2000-01-01', validUntilExclusive='2100-01-01',
                                 updatedOn='2000-01-01') for row in SEED])
        os.environ['ADVISOR_DB'] = db  # advisor constructs its default app at import.
        from advisor import create_app
        sock.bind(('127.0.0.1', 0))
        base = f'http://127.0.0.1:{sock.getsockname()[1]}'
        server = uvicorn.Server(uvicorn.Config(create_app(db), log_level='warning'))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started:
                if not thread.is_alive() or time.monotonic() > deadline:
                    raise RuntimeError('Disposable server did not start')
                time.sleep(.025)
            yield base
        finally:
            server.should_exit = True
            thread.join(10)


def button(root, name):
    return root.get_by_role('button', name=name, exact=isinstance(name, str))


def screenshots(page, directory, stage):
    for width in WIDTHS:
        page.set_viewport_size({'width': width, 'height': 844})
        page.evaluate('window.scrollTo(0, 0)')
        page.screenshot(path=directory / f'{stage}-{width}.png', animations='disabled', full_page=True)
        for frame in page.frames:
            if frame != page.main_frame and not frame.frame_element().is_visible():
                continue
            viewport, content = frame.evaluate('''() => [document.documentElement.clientWidth,
                Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)]''')
            assert viewport == width and content <= width, (stage, frame.url, width, viewport, content)
    page.set_viewport_size({'width': 390, 'height': 844})


def rank(page, rows):
    articles = page.locator('#buyResults').get_by_role('article')  # excludes collapsed rows
    expect(articles).to_have_count(len(rows))
    for i, (name, rubles) in enumerate(rows):
        expect(articles.nth(i).get_by_role('heading').first).to_contain_text(name)
        expect(articles.nth(i)).to_contain_text(re.compile(r'(?<![\d,])' + rubles + r'(?:,00)?\s*₽'))


def category(page, name):
    grid = page.locator('#categoryGrid')
    if not grid.is_visible():
        button(page, re.compile('Изменить')).click()
    tile = button(grid, name)
    if not tile.is_visible():
        button(page, 'Все категории').click()
    tile.click()
    expect(grid).to_be_hidden()
    expect(button(page, re.compile('Изменить'))).to_contain_text(name)


def catalog_scenario(page, directory):
    buy = page.locator('#buyPanel')
    amount, status = page.locator('#buyAmount'), page.locator('#buyStatus')
    page.locator('#openBuy').click()
    expect(amount).not_to_be_focused()
    expect(button(buy, 'Мои карты')).to_have_attribute('aria-pressed', 'true')
    expect(button(buy, 'Весь каталог')).to_be_visible()
    screenshots(page, directory, 'categories')
    category(page, 'Супермаркеты')
    amount.fill('2 500')
    expect(status).to_contain_text('Кошелёк пуст')
    expect(buy.get_by_role('article')).to_have_count(0)
    button(buy, 'Посмотреть в каталоге').click()
    top = [('Карта B', '150'), ('Карта A', '100'), ('Карта C', '100')]
    rank(page, top)
    screenshots(page, directory, 'top3')
    card_a = buy.get_by_role('article').nth(1)
    card_a.get_by_text('Условия', exact=True).click()
    for evidence in ['10%', 'применён', 'Актуальность', '01.01.2000']:
        expect(card_a.locator('details[open]')).to_contain_text(evidence)
    buy.get_by_text(re.compile('^Все подходящие карты')).click()
    rank(page, top + [('Карта D', '50')])
    category(page, 'Кафе')
    expect(amount).to_have_value('2 500')
    rank(page, [('Карта D', '200')])
    amount.fill('99,99')
    expect(status).to_contain_text('подходящих условий нет')
    rank(page, [])
    amount.fill('100')
    rank(page, [('Карта D', '8')])
    category(page, 'Супермаркеты')
    amount.fill('2500')
    rank(page, top)

    sent = []
    page.on('request', lambda req: sent.append(req.post_data_json) if req.url.endswith('/api/recommendations') else None)
    for raw, hint in [('', 'Введите'), ('0', 'нуля'), ('-1', 'отрицатель'), ('1.234', 'двух'),
                      ('10000000001', 'Максимальная'), ('2,', 'целиком')]:
        amount.fill(raw)
        expect(status).to_contain_text(hint)
        rank(page, [])
    # Cross the debounce interval once, then use a valid calculation as a synchronization point.
    for raw in ('2500,50', '2500.50'):
        with page.expect_response(lambda r: r.url.endswith('/api/recommendations')) as response:
            amount.fill(raw)
        assert response.value.request.post_data_json['amountKopecks'] == 250050
        rank(page, [('Карта B', '150,03'), ('Карта C', '100,02'), ('Карта A', '100')])
    assert [body['amountKopecks'] for body in sent] == [250050, 250050], sent
    page.route(REC, lambda route: route.fulfill(status=503, body='{}'), times=1)
    amount.fill('2500')
    retry = button(buy, re.compile('Повторить'))
    expect(retry).to_be_visible()
    rank(page, [])
    retry.click()
    rank(page, top)


def record_once(page, base, card_name):
    paid = page.get_by_label('Какой картой вы оплатили?')
    expect(paid).to_have_value('')
    paid.select_option(label=card_name)
    submit = button(page, 'Записать покупку')
    bodies = []

    def lose_first_response(route):
        bodies.append(route.request.post_data_json)
        if len(bodies) == 1:
            # Commit to the real DB first; drop only the response on the way to the UI.
            upstream = route.fetch(max_retries=0)
            assert upstream.status == 201, upstream.text()
            route.abort()
        else:
            route.continue_()

    stats = base + '/api/me/stats'
    assert page.request.get(stats).json()['count'] == 0
    page.route('**/api/me/purchases', lose_first_response)
    submit.click()
    expect(page.get_by_text(re.compile('Не удалось подтвердить запись'))).to_be_visible()
    submit.click()
    expect(page.locator('#buyStatus')).to_contain_text('Покупка записана')
    assert len(bodies) == 2 and bodies[0] == bodies[1] and bodies[0]['requestId'], bodies
    report = page.request.get(stats).json()
    assert report['count'] == 1 and report['purchases'][0]['amountKopecks'] == bodies[0]['amountKopecks'], report
    button(page, 'Открыть историю').click()
    history = page.locator('#historyPanel')
    expect(history.get_by_role('heading', name='История покупок')).to_be_visible()
    expect(history).to_contain_text(card_name)


def personal_scenario(page, base, directory):
    button(page.locator('#buyPanel'), 'Назад').click()
    expect(page.locator('#hero')).to_be_visible()
    page.locator('#openCards').click()
    cards = page.locator('#cardsPanel')
    expect(cards).to_be_visible()
    add = page.locator('#addDialog')
    cards.locator('#openCatalog').click()
    button(add, 'Выбрать банк').click()
    button(add, 'Учебный каталог').click()
    add.locator('#newBank').select_option('A')
    button(add, 'Добавить карту').click()
    expect(add).to_be_hidden()
    expect(page.locator('#carouselDetails')).to_contain_text('Карта A')
    expect(page.locator('#carouselPrev')).to_be_hidden()
    expect(page.locator('#carouselNext')).to_be_hidden()
    if page.locator('#cardMenu').is_visible():
        button(cards, 'Действия с картой').click()
    cards.locator('#openCatalog').click()
    button(add, 'Выбрать банк').click()
    search = add.get_by_role('searchbox')
    search.fill('несуществующийбанк')
    expect(button(add, 'Добавить карту')).to_be_disabled()
    search.fill('ВТБ')
    add.locator('#bankSuggestions').get_by_role('option', name='ВТБ', exact=True).click()
    button(add, 'Добавить карту').click()
    expect(add).to_be_hidden()
    details = page.locator('#carouselDetails')
    expect(details).to_contain_text('ВТБ')
    if page.locator('#cardMenu').is_visible():
        button(cards, 'Действия с картой').click()
    carousel = page.locator('#cardCarousel')
    carousel.focus()
    carousel.press('ArrowLeft')
    expect(details).to_contain_text('Карта A')
    carousel.press('ArrowRight')
    expect(details).to_contain_text('ВТБ')
    button(cards, 'Действия с картой').click()
    button(cards, 'Добавить условия кэшбэка').click()
    review = page.locator('#catalogDialog')
    button(review, re.compile('подключённые')).click()
    button(review, 'Ввести условия вручную').click()
    review.locator('#reviewSlots').fill('2', force=True)
    for i, (label, code, rate) in enumerate([('Транспорт', 'transport', '15'), ('На все покупки', 'all', '1')]):
        if i:
            button(review, 'Добавить строку').click()
        row = review.locator('#reviewRows fieldset').nth(i)
        details = row.locator('details')
        if not details.get_attribute('open'):
            row.locator('summary').click()
        row.locator('[data-key=label]').fill(label)
        row.locator('[data-key=categoryId]').fill(code)
        row.locator('[data-key=rateBps]').fill(rate)
        row.locator('[data-key=include]').check()
    screenshots(page, directory, 'manual-conditions')
    button(review, 'Сохранить категории').click()
    expect(review).to_be_hidden()
    page.reload()
    expect(cards).to_be_visible()
    button(cards, 'Назад').click()
    page.locator('#openBuy').click()
    button(page.locator('#buyPanel'), 'Мои карты').click()
    category(page, 'Транспорт')
    amount = page.locator('#buyAmount')
    amount.fill('1000')
    rank(page, [('ВТБ', '150')])  # Exact rule, not 15% + 1%.
    category(page, 'АЗС')
    rank(page, [('ВТБ', '10')])  # Only this card has a fallback rule.
    amount.fill('0,01')
    rank(page, [('ВТБ', '0')])
    expect(page.locator('#buyStatus')).to_contain_text('0 ₽')
    category(page, 'Супермаркеты')
    amount.fill('2500')
    rank(page, [('Карта A', '100'), ('ВТБ', '25')])
    record_once(page, base, 'ВТБ')
    screenshots(page, directory, 'history')


def run(chromium, directory, revision):
    directory.mkdir(parents=True, exist_ok=True)
    with isolated_server() as base, sync_playwright() as runtime:
        browser = runtime.chromium.launch(executable_path=chromium)
        try:
            context = browser.new_context(viewport={'width':390, 'height':844}, locale='ru-RU',
                                          reduced_motion='reduce', service_workers='block')
            denied, errors = [], []

            def local_only(route):
                url = route.request.url
                if not url.startswith(base + '/') or url.endswith(('/cashback-screenshot', '/stats/comment')):
                    denied.append(url)
                    route.abort()
                else:
                    route.continue_()
            context.route('**/*', local_only)
            page = context.new_page()
            page.set_default_timeout(6500)
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                page.goto(base)
                start = page.frame_locator('#welcomeScreen').locator('#start')
                expect(start).to_be_visible()
                screenshots(page, directory, 'welcome')
                start.click()
                auth = page.locator('#authForm')
                login, password = 'qa_' + uuid4().hex[:10], uuid4().hex
                auth.get_by_label('Логин').fill(login)
                auth.get_by_label('Пароль', exact=True).fill(password)
                button(auth, re.compile('Создать|Зарегистр')).click()
                expect(page.locator('#openBuy')).to_be_visible()
                screenshots(page, directory, 'home-empty')
                expect(page.locator('#openBuy')).to_have_accessible_name('Сравнить карты')
                catalog_scenario(page, directory)
                personal_scenario(page, base, directory)
                assert not denied and not errors, (denied, errors)
            except Exception:
                page.screenshot(path=directory/'failure.png', animations='disabled', full_page=True)
                raise
        finally:
            browser.close()
        if revision:
            subprocess.run([sys.executable, str(ROOT/'deploy'/'smoke.py'), base, '--revision', revision], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chromium-executable', help='Optional installed Chrome/Edge executable')
    parser.add_argument('--artifacts', type=Path, default=None)
    parser.add_argument('--revision', help='Verify the revision when running a release archive')
    args = parser.parse_args()
    artifacts = args.artifacts or Path(tempfile.mkdtemp(prefix='advisor-screens-'))
    print(f'Browser screenshots: {artifacts.resolve()}', flush=True)
    run(args.chromium_executable, artifacts, args.revision)
    print('Advisor visible wallet acceptance passed.')
