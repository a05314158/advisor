"""Run the redesigned wallet purchase flow in Chromium."""
import argparse
import re
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
        page.locator('#openProfile').click()
        expect(page.locator('#profileCardCount')).to_have_text('0')
        expect(page.locator('#profileStatsStatus')).to_contain_text('Запишите покупку')
        expect(page.locator('#profileStatsBody')).to_be_hidden()
        page.locator('#profileBack').click()
        page.locator('#openBuy').click()
        page.locator('#buyAll').click()
        page.locator('#categoryGrid button[data-id="supermarkets"]').click()
        page.locator('#buyAmount').fill('2500')
        results = page.locator('#buyResults article')
        expect(results.locator('strong')).to_have_text(['Карта B', 'Карта A', 'Карта C'])
        results.nth(1).get_by_text('Условия', exact=True).click()
        expect(results.nth(1)).to_contain_text('После лимита по условию')
        expect(results.nth(1)).to_contain_text('Сведения от')
        page.get_by_text('Все подходящие карты', exact=True).click()
        expect(page.locator('#otherBuyResults')).to_contain_text('Карта D')
        page.locator('#categoryGrid button[data-id="cafe"]').click()
        expect(results.locator('strong')).to_have_text(['Карта D'])
        page.get_by_text('Карты и условия каталога', exact=True).click()
        expect(page.locator('#catalogCards article')).to_have_count(1)
        page.get_by_role('button', name='Добавить в кошелёк').click()
        expect(page.get_by_role('button', name='Убрать из кошелька')).to_be_visible()
        page.locator('#buyBack').click()
        page.locator('#openCards').click()

        # Create a manual card and its active rule through the real mobile UI.
        page.locator('#addCardBtn').click()
        page.locator('#newBankSearch').fill('Т-Банк')
        page.locator('#newBank').select_option('tbank')
        page.locator('#addCardForm button[type="submit"]').click()
        expect(page.locator('#carouselTrack')).to_contain_text('Т-Банк')
        page.locator('#addCashbackBtn').click()
        page.locator('#bankId').select_option('tbank')
        page.locator('#manualDraft').click()
        page.locator('#reviewRows [data-key="label"]').fill('Супермаркеты')
        page.locator('#reviewRows [data-key="rateBps"]').fill('10')
        page.locator('#reviewRows [data-key="limitKopecks"]').fill('120')
        page.locator('#saveReview').click()
        expect(page.locator('#catalogDialog')).to_be_hidden()
        page.locator('#carouselNext').click()
        expect(page.locator('#carouselDetails')).to_contain_text('Супермаркеты 10%')
        page.get_by_role('button', name='Условия и лимит').click()
        page.locator('#editMonthlyLimit').fill('500')
        page.locator('#editMonthlyUsed').fill('410')
        page.get_by_role('button', name='Сохранить лимит').click()
        expect(page.locator('#editCardDialog')).to_be_hidden()

        # Populate the wallet without requiring live screenshot recognition.
        for name, rate in [('ВТБ', 300), ('Моя карта', 100)]:
            response = page.request.post(base + '/api/me/manual-cards', data={
                'name': name,
                'rules': [{'categoryId': 'supermarkets', 'rateBps': rate, 'limitKopecks': None}],
            })
            assert response.status == 201, response.text()
        page.reload()
        page.locator('#openBuy').click()
        page.locator('#categoryGrid button[data-id="supermarkets"]').click()
        page.locator('#buyAmount').fill('2500')
        results = page.locator('#buyResults article')
        expect(results.locator('strong')).to_have_text(['Т-Банк', 'ВТБ', 'Карта D'])
        expect(results.first).to_contain_text(re.compile(r'90(?:,00)?\s*₽'))
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

        page.locator('#buyBack').click()
        page.locator('#openCards').click()
        page.locator('#carouselNext').click()
        expect(page.locator('#carouselDetails')).to_contain_text('Супермаркеты 10%')
        page.get_by_role('button', name='Условия и лимит').click()
        page.locator('#editRateValue').fill('2')
        page.get_by_role('button', name='Сохранить ставку').click()
        expect(page.locator('#carouselDetails')).to_contain_text('Супермаркеты 2%')
        page.reload()
        page.locator('#openBuy').click()
        page.locator('#categoryGrid button[data-id="supermarkets"]').click()
        page.locator('#buyAmount').fill('2500')
        expect(results.locator('strong')).to_have_text(['ВТБ', 'Карта D', 'Т-Банк'])
        bank_card = results.filter(has_text='Т-Банк')
        bank_card.get_by_text('Условия', exact=True).click()
        expect(bank_card).to_contain_text(re.compile(r'Остаток месяца: 90(?:,00)?\s*₽'))
        bank_card.get_by_role('button', name='Выбрать').click()
        expect(page.locator('#buyStatus')).to_have_text('Покупка записана')
        page.reload()
        expect(page.locator('#openBuy')).to_be_visible()
        stats = page.request.get(base + '/api/me/stats').json()
        assert stats['count'] == 1 and stats['calculatedKopecks'] == 5_000, stats
        page.locator('#openBuy').click()
        page.locator('#categoryGrid button[data-id="supermarkets"]').click()
        page.locator('#buyAmount').fill('2500')
        results.filter(has_text='ВТБ').get_by_role('button', name='Выбрать').click()
        expect(page.locator('#buyStatus')).to_have_text('Покупка записана')
        page.locator('#openProfile').click()
        profile = page.locator('#profilePanel')
        expect(profile).to_be_visible()
        expect(page.locator('#profileCardCount')).to_have_text('4')
        expect(page.locator('#profilePurchaseCount')).to_have_text('2')
        expect(page.locator('#profileCashback')).to_have_text(re.compile(r'125(?:,00)?\s*₽'))
        expect(page.locator('#profileLegend li')).to_have_count(2)
        expect(page.locator('#profileLegend li').first).to_contain_text('ВТБ')
        assert 'conic-gradient' in page.locator('#profileDonut').get_attribute('style')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.locator('#profileBack').click()
        page.locator('#openCards').click()
        expect(profile).to_be_hidden()
        expect(page.locator('#cardsPanel').get_by_role('button', name='План кэшбэка на месяц')).to_have_count(0)
        assert not errors, errors
        browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_url')
    parser.add_argument('--chromium-executable')
    args = parser.parse_args()
    check(args.base_url.rstrip('/'), args.chromium_executable)
    print('PASS: mobile wallet, saved cards and purchases, cashback ranking, bank link and profile dashboard.')
