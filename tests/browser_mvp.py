"""Run the redesigned wallet purchase flow in Chromium."""
import argparse
import re
from datetime import UTC, datetime
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright


def check(base, chromium=None):
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(executable_path=chromium)
        page = browser.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(base)
        page.frame_locator('#welcomeScreen').locator('#start').click()
        page.locator('#authLogin').fill('wallet_' + uuid4().hex[:16])
        page.locator('#authPassword').fill(uuid4().hex)
        page.locator('#authSubmit').click()
        expect(page.locator('#openBuy')).to_be_visible()

        # Populate the wallet without requiring live screenshot recognition.
        for name, rate in [('ВТБ', 400), ('Моя карта', 200)]:
            response = page.request.post(base + '/api/me/manual-cards', data={
                'name': name,
                'rules': [{'categoryId': 'supermarkets', 'rateBps': rate, 'limitKopecks': None}],
            })
            assert response.status == 201, response.text()
        response = page.request.post(base + '/api/me/cashback-confirm', data={
            'bankId': 'tbank',
            'month': datetime.now(UTC).strftime('%Y-%m'),
            'mode': 'active',
            'slots': None,
            'requestId': uuid4().hex,
            'rules': [{
                'label': 'Супермаркеты', 'categoryId': 'supermarkets', 'rateBps': 1000,
                'limitKopecks': 12_000, 'minAmountKopecks': 1, 'selected': True, 'uncertain': False,
            }],
        })
        assert response.ok, response.text()
        page.reload()
        page.locator('#openBuy').click()
        page.locator('#categoryGrid button[data-id="supermarkets"]').click()
        page.locator('#buyAmount').fill('2500')
        results = page.locator('#buyResults article')
        expect(results.locator('strong')).to_have_text(['Т-Банк', 'ВТБ', 'Моя карта'])
        expect(results.first).to_contain_text(re.compile(r'120(?:,00)?\s*₽'))
        first_link = results.first.get_by_role('link', name=re.compile('Открыть веб-кабинет'))
        expect(first_link).to_have_attribute('href', 'https://www.tbank.ru/login/')
        expect(results.nth(1).get_by_role('link')).to_have_attribute('href', 'https://online.vtb.ru/')
        expect(results.nth(2).get_by_role('link')).to_have_count(0)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')

        page.context.route('https://www.tbank.ru/login/', lambda route: route.fulfill(body='Bank destination'))
        with page.expect_popup() as opened:
            first_link.click()
        opened.value.wait_for_load_state()
        assert opened.value.url == 'https://www.tbank.ru/login/'
        opened.value.close()
        assert page.request.get(base + '/api/me/stats').json()['count'] == 0

        results.first.get_by_role('button', name='Выбрать').click()
        expect(page.locator('#buyStatus')).to_have_text('Покупка записана')
        page.reload()
        expect(page.locator('#openBuy')).to_be_visible()
        stats = page.request.get(base + '/api/me/stats').json()
        assert stats['count'] == 1 and stats['calculatedKopecks'] == 12_000, stats
        assert not errors, errors
        browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_url')
    parser.add_argument('--chromium-executable')
    args = parser.parse_args()
    check(args.base_url.rstrip('/'), args.chromium_executable)
    print('PASS: mobile wallet, persisted cards, ranked and capped cashback, bank link and saved purchase.')
