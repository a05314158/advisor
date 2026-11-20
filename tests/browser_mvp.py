"""Run the defense flow in Chromium against a disposable Advisor instance."""
import argparse
import re
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright


def check(base, chromium=None):
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(executable_path=chromium)
        try:
            page = browser.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base)
            assert page.request.get(base + '/api/nearby').status == 404

            scope, category = page.locator('#scope'), page.locator('#category')
            category.select_option('supermarkets')
            page.locator('#amount').fill('2500')
            expect(page.locator('#compare')).to_be_enabled()
            scope.select_option('all')
            page.locator('#compare').click()
            expect(page.locator('#results h3').first).to_have_text(re.compile(r'Карта B$'))
            expect(page.locator('#results .return').first).to_have_text(re.compile(r'150(?:,00)?\s?₽'))
            expect(page.get_by_text('Оплатить по ссылке продавца')).to_have_count(0)
            page.locator('#results details summary', has_text='Все подходящие карты').click()
            expect(page.locator('#results h3', has_text='Карта D')).to_be_visible()
            card_a = page.locator('#results article', has_text='Карта A').first
            card_a.get_by_text('Условия', exact=True).click()
            expect(card_a.get_by_text(re.compile(r'Действует с'))).to_be_visible()
            expect(card_a.get_by_text('Как рассчитан кэшбэк')).to_be_visible()
            expect(card_a.get_by_text(re.compile(r'После лимита на покупку: 100'))).to_be_visible()
            category.select_option('cafe')
            page.locator('#compare').click()
            expect(page.locator('#results h3').first).to_have_text(re.compile(r'Карта D$'))

            credentials = {'username':'defense-' + uuid4().hex[:12], 'password':uuid4().hex}
            response = page.request.post(base + '/api/auth/register', data=credentials)
            assert response.status == 201, response.text()
            for name, rate in [('Первая',1000), ('Вторая',400), ('Третья',380), ('Четвёртая',350)]:
                bank = {'Первая': 'Т‑Банк', 'Вторая': 'Альфа‑Банк'}.get(name, 'Учебный банк')
                body = {'name':name, 'bankName':bank, 'rules':[{'categoryName':'Такси','rateBps':rate}]}
                if name == 'Первая':
                    body.update(monthlyLimitKopecks=300_000, monthlyUsedKopecks=288_000)
                response = page.request.post(base + '/api/me/manual-cards', data=body)
                assert response.status == 201, response.text()
            page.reload()
            card = page.locator('#my-list article', has_text='Первая')
            expect(card).to_be_attached()
            scope.select_option('mine')
            category.select_option('taxi')
            page.locator('#amount').fill('2500')
            page.locator('#compare').click()
            expect(page.locator('#results h3').first).to_have_text(re.compile(r'Первая$'))
            winner = page.locator('#results .winner')
            expect(winner.get_by_role('link', name='Открыть Т‑Банк в браузере')).to_have_attribute(
                'href', 'https://www.tbank.ru/login/')
            winner.get_by_text('Оплатить по ссылке продавца', exact=True).click()
            payment = winner.get_by_label('Ссылка на оплату от продавца')
            checkouts = winner.get_by_role('link', name=re.compile(r'Перейти к оплате'))
            fake_qr = 'https://qr.nspk.ru/' + 'A' * 32
            tpay = 'https://o.tbank.ru/tpay/test-fixture'
            for url in ['https://example.invalid/pay', fake_qr + '?redirect=test',
                        fake_qr + '?type=02&bank=000000000001&sum=10000&cur=RUB&crc=A1B2']:
                payment.fill(url)
                expect(checkouts).to_have_count(0)
            expect(winner.get_by_text(re.compile('Сумма в ссылке отличается'))).to_be_visible()
            old_format = fake_qr + '?type=02&bank=000000000001&sum=250000&cur=RUB&crc=A1B2'
            payment.fill(old_format)
            expect(winner.get_by_role('link', name='Перейти к оплате через СБП')).to_have_attribute('href', old_format)
            payment.fill(tpay)
            link = winner.get_by_role('link', name='Перейти к оплате через T‑Pay')
            expect(link).to_have_attribute('href', tpay)
            page.route(tpay, lambda route: route.fulfill(status=200, body='Payment handoff test'))
            link.click()
            expect(page).to_have_url(tpay)
            page.go_back(wait_until='load')
            scope.select_option('mine')
            category.select_option('taxi')
            page.locator('#amount').fill('2500')
            page.locator('#compare').click()
            expect(page.locator('#results h3').first).to_have_text(re.compile(r'Первая$'))
            card.get_by_text('Изменить ставку', exact=True).click()
            card.get_by_label('Новая ставка, %').fill('3')
            card.get_by_role('button', name='Сохранить ставку').click()
            expect(page.locator('#cards-status')).to_have_text(re.compile(r'Ставка сохранена'))
            page.locator('#compare').click()
            expect(page.locator('#results > article')).to_have_count(3)
            expect(page.locator('#results h3').first).to_have_text(re.compile(r'Вторая$'))
            expect(winner.get_by_role('link', name='Открыть Альфа‑Банк в браузере')).to_have_attribute(
                'href', 'https://web.alfabank.ru/')
            winner.get_by_text('Оплатить по ссылке продавца', exact=True).click()
            payment.fill(tpay)
            expect(checkouts).to_have_count(0)
            payment.fill(fake_qr)
            expect(winner.get_by_role('link', name='Перейти к оплате через СБП')).to_have_attribute('href', fake_qr)
            page.get_by_role('button', name='Записать эту покупку').click()
            expect(page.locator('#purchase-amount')).to_have_value('2500')
            expect(page.locator('#purchase-category')).to_have_value('Такси')
            expect(page.locator('#purchase-card')).to_have_value('')
            page.reload()
            expect(card.get_by_text(re.compile(r'Такси.*3%'))).to_be_visible()
            card.get_by_text('Месячный лимит', exact=True).click()
            expect(card.get_by_text(re.compile(r'Известный остаток: 120'))).to_be_visible()

            requests = []

            def intercept(route):
                requests.append(route.request.headers['idempotency-key'])
                if len(requests) == 1:
                    assert route.fetch().status == 201
                    route.abort()
                else:
                    route.continue_()

            page.route('**/api/me/purchases', intercept)
            page.locator('#purchase-entry summary').click()
            page.locator('#purchase-amount').fill('2500')
            page.locator('#purchase-category').fill('Такси')
            page.locator('#purchase-card').select_option(label='Первая')
            page.locator('#purchase-form button').click()
            expect(page.locator('#purchase-status')).to_have_text('Не удалось сохранить покупку.')
            page.locator('#purchase-form button').click()
            expect(page.locator('#purchase-status')).to_have_text('')
            report = page.request.get(base + '/api/me/spending').json()
            assert (report['count'], report['totalKopecks']) == (1, 250000), report
            assert report['purchases'][0]['cashbackComparison']['differenceKopecks'] == 2500
            page.get_by_text('Журнал покупок', exact=True).click()
            expect(page.get_by_text(re.compile(r'Можно было бы вернуть на 25'))).to_be_visible()
            assert len(requests) == 2 and requests[0] == requests[1]
            assert not errors, errors
        finally:
            browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_url')
    parser.add_argument('--chromium-executable')
    args = parser.parse_args()
    check(args.base_url.rstrip('/'), args.chromium_executable)
    print('Advisor browser defense scenario passed.')
