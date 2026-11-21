"""Exercise the current wallet UI against the shared API."""
import argparse
from uuid import uuid4
from playwright.sync_api import expect, sync_playwright


def check(base, chromium=None):
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(executable_path=chromium)
        try:
            page = browser.new_page(viewport={'width': 390, 'height': 844})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base)
            expect(page.locator('#welcomeScreen')).to_be_visible()
            # Enter registration through the existing welcome action.
            page.frame_locator('#welcomeScreen').locator('#start').click()
            page.locator('#authLogin').fill('wallet-' + uuid4().hex[:12])
            page.locator('#authPassword').fill(uuid4().hex)
            page.locator('#authSubmit').click()
            expect(page.locator('#appScreen')).to_be_visible()
            response = page.request.post(base + '/api/me/manual-cards', data={
                'name': 'Тестовая карта', 'bankName': 'Т-Банк',
                'rules': [{'categoryId': 'supermarkets', 'rateBps': 500}]})
            assert response.status == 201, response.text()
            page.reload()
            expect(page.locator('#cardsSubtitle')).to_contain_text('1 карта')
            page.locator('#openBuy').click()
            page.locator('#categoryGrid [data-id="supermarkets"]').click()
            page.locator('#buyAmount').fill('2500')
            expect(page.locator('#buyResults')).to_contain_text('125')
            page.locator('#buyResults .pick').click()
            expect(page.locator('#buyStatus')).to_have_text('Покупка записана')
            report = page.request.get(base + '/api/me/spending').json()
            assert report['count'] == 1 and report['totalKopecks'] == 250000, report
            assert not errors, errors
        finally:
            browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_url')
    parser.add_argument('--chromium-executable')
    args = parser.parse_args()
    check(args.base_url.rstrip('/'), args.chromium_executable)
    print('Advisor wallet browser scenario passed.')
