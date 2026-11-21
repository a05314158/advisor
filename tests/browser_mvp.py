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
            page.goto(base + '/classic')
            assert page.request.get(base + '/api/nearby').status == 404

            scope, category = page.locator('#scope'), page.locator('#category')
            category.select_option('supermarkets')
            page.locator('#amount').fill('2500')
            expect(page.locator('#compare')).to_be_enabled()
            scope.select_option('all')
            page.locator('#compare').click()
            expect(page.locator('#results h3').first).to_have_text(re.compile(r'Карта B$'))
            expect(page.locator('#results .return').first).to_have_text(re.compile(r'150(?:,00)?\s?₽'))
            expect(page.get_by_text('Оплатить через T‑Pay')).to_have_count(0)
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
            page.reload()
            form = page.locator('#manual-form')
            page.get_by_text('Добавить карту', exact=True).click()
            total = page.get_by_role('button', name=re.compile(r'Все банки \(\d{3}\)'))
            expect(total).to_be_visible()
            expect(page.locator('.bank-tile')).to_have_count(6)
            total.click()
            expect(page.locator('.bank-tile')).to_have_count(30)
            bank_search = page.get_by_label('Найти банк')
            bank_search.fill('модуль')
            expect(page.get_by_role('button', name='Модульбанк', exact=True)).to_be_visible()
            bank_search.fill('1927')
            expect(page.get_by_role('button', name='Модульбанк', exact=True)).to_be_visible()
            page.get_by_role('button', name='Другой банк', exact=True).click()
            expect(form.get_by_label('Название банка')).to_be_visible()
            expect(form.get_by_label('Название карты (без номера)')).to_be_visible()
            form.get_by_role('button', name='Сменить банк').click()
            search = page.get_by_label('Найти банк')
            search.fill('неизвестный')
            expect(page.get_by_text('Банк не найден.', exact=False)).to_be_visible()
            search.fill('тинькофф')
            expect(page.locator('.bank-tile')).to_have_count(1)
            page.get_by_role('button', name='Т‑Банк', exact=True).click()
            expect(form.get_by_label('Название карты (без номера)')).to_be_hidden()

            expect(form.get_by_label('Категория', exact=True)).to_be_focused()
            form.get_by_label('Общий лимит кэшбэка за месяц, ₽').fill('3000')
            form.get_by_label('Уже начислено в этом месяце, ₽').fill('2880')
            form.get_by_label('Категория', exact=True).fill('так')
            form.get_by_role('button', name='Такси', exact=True).click()
            expect(form.get_by_label('Категория', exact=True)).to_have_value('Такси')
            form.get_by_label('Кэшбэк, %', exact=True).fill('10')
            form.get_by_role('button', name='Ещё категория').click()
            form.get_by_label('Категория', exact=True).last.fill('Своя категория')
            form.get_by_label('Кэшбэк, %', exact=True).last.fill('1')
            form.get_by_role('button', name='Сохранить карту').click()
            expect(page.locator('#my-list article', has_text='Т‑Банк')).to_be_visible()
            expect(page.locator('#my-list article', has_text='Т‑Банк')).to_contain_text('Своя категория')
            for name, rate in [('Вторая',400), ('Третья',380), ('Четвёртая',350)]:
                bank = 'Альфа‑Банк' if name == 'Вторая' else 'Учебный банк'
                body = {'name':name, 'bankName':bank, 'rules':[{'categoryName':'Такси','rateBps':rate}]}
                response = page.request.post(base + '/api/me/manual-cards', data=body)
                assert response.status == 201, response.text()
            page.reload()
            card = page.locator('#my-list article', has_text='Т‑Банк')
            expect(card).to_be_attached()
            scope.select_option('mine')
            category.select_option('taxi')
            page.locator('#amount').fill('2500')
            page.locator('#compare').click()
            expect(page.locator('#results h3').first).to_have_text(re.compile(r'Т‑Банк$'))
            winner = page.locator('#results .winner')
            expect(winner.get_by_role('link', name='Открыть Т‑Банк в браузере')).to_have_attribute(
                'href', 'https://www.tbank.ru/login/')
            winner.get_by_text('Оплатить через T‑Pay', exact=True).click()
            payment = winner.get_by_label('Ссылка T‑Pay от продавца')
            checkouts = winner.get_by_role('link', name=re.compile(r'Перейти к оплате'))
            fake_qr = 'https://qr.nspk.ru/' + 'A' * 32
            tpay = 'https://o.tbank.ru/tpay/test-fixture'
            for url in ['https://example.invalid/pay', fake_qr, tpay + '?redirect=test']:
                payment.fill(url)
                expect(checkouts).to_have_count(0)
            expect(winner.get_by_text(re.compile('Ссылки СБП здесь не подходят'))).to_be_visible()
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
            expect(page.locator('#results h3').first).to_have_text(re.compile(r'Т‑Банк$'))
            card.get_by_text('Изменить ставку', exact=True).click()
            card.get_by_label('Новая ставка, %').fill('3')
            card.get_by_role('button', name='Сохранить ставку').click()
            expect(page.locator('#cards-status')).to_have_text(re.compile(r'Ставка сохранена'))
            page.locator('#compare').click()
            expect(page.locator('#results > article')).to_have_count(3)
            expect(page.locator('#results h3').first).to_have_text(re.compile(r'Вторая$'))
            expect(winner.get_by_role('link', name='Открыть Альфа‑Банк в браузере')).to_have_attribute(
                'href', 'https://web.alfabank.ru/')
            expect(winner.get_by_text('Оплатить через T‑Pay', exact=True)).to_have_count(0)
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
            page.locator('#purchase-card').select_option(label='Т‑Банк')
            page.locator('#purchase-form button').click()
            expect(page.locator('#purchase-status')).to_have_text('Не удалось сохранить покупку.')
            page.locator('#purchase-form button').click()
            expect(page.locator('#purchase-status')).to_have_text('')
            report = page.request.get(base + '/api/me/spending').json()
            assert (report['count'], report['totalKopecks']) == (1, 250000), report
            assert report['purchases'][0]['cashbackComparison']['differenceKopecks'] == 2500
            page.get_by_text('Журнал покупок', exact=True).click()
            expect(page.get_by_text(re.compile(r'Можно было бы вернуть на 25'))).to_be_visible()
            accrued = page.get_by_label('Фактически начислено, ₽')
            accrued.fill('0')
            page.get_by_role('button', name='Сохранить начисление').click()
            expect(page.get_by_text('заполнено покупок: 1 из 1', exact=False)).to_be_visible()
            expect(accrued).to_have_value('0')
            accrued.fill('75,25')
            page.get_by_role('button', name='Сохранить начисление').click()
            expect(page.get_by_text(re.compile(r'Фактический кэшбэк по покупкам этого месяца: 75,25'))).to_be_visible()
            assert len(requests) == 2 and requests[0] == requests[1]
            from datetime import UTC, datetime
            second = page.request.post(base + '/api/me/purchases', data={
                'date':datetime.now(UTC).date().isoformat(), 'categoryName':'Такси',
                'merchant':'Черновик', 'amountKopecks':10000,
            })
            assert second.status == 201
            page.reload()
            page.get_by_text('Журнал покупок', exact=True).click()
            draft = page.locator('#spending-report .card', has_text='Черновик').get_by_label('Фактически начислено, ₽')
            draft.fill('39')
            existing = page.locator('#spending-report div.card').filter(has_text=re.compile(r'2\s500')).last
            existing.get_by_role('button', name='Сохранить начисление').click()
            expect(page.get_by_text('заполнено покупок: 1 из 2', exact=False)).to_be_visible()
            expect(draft).to_have_value('39')

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
