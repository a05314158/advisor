"""Exercise the wallet UI with a new account on a disposable local instance. No AI calls."""
import argparse
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright


def check(base, chromium=None):
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(executable_path=chromium)
        try:
            page = browser.new_page(viewport={'width': 390, 'height': 720}, is_mobile=True, has_touch=True)
            page.set_default_timeout(5000)
            errors, blocked = [], []
            page.on('pageerror', lambda error: errors.append(str(error)))
            def block_ai(route):
                blocked.append(route.request.url)
                route.abort()
            page.route('**/api/me/cashback-screenshot', block_ai)
            page.route('**/api/me/stats/comment', block_ai)
            response = page.request.post(base + '/api/auth/register', data={'login':'plan_' + uuid4().hex[:12], 'password':uuid4().hex})
            assert response.status in (200, 201), response.text()
            page.goto(base)
            loc = lambda ident: page.locator('#' + ident)
            loc('openCards').click()
            # Simulate only the OCR response; never send an image to the service.
            loc('addCashbackBtn').click()
            loc('chooseActive').click()
            page.route('**/api/me/cashback-screenshot', lambda r: r.fulfill(json={'rules':[{'label':'Кафе','selected':None,'uncertain':True}]}))
            loc('cashbackShot').set_input_files({'name':'synthetic.png','mimeType':'image/png','buffer':b'\x89PNG\r\n\x1a\nsynthetic'})
            loc('confirmCard').click()
            expect(loc('reviewMonth')).to_have_value('')
            expect(loc('reviewMonthText')).to_contain_text('Выберите месяц')
            expect(loc('reviewRows').locator('[data-key=include]')).not_to_be_checked()
            loc('closeCatalog').click()
            expect(loc('discardDialog')).to_be_visible()
            loc('discardLeave').click()
            expect(loc('addCashbackBtn')).to_be_focused()
            loc('cardsBack').click()
            loc('openPlan').click(force=True)
            month = page.evaluate("""() => {const d = new Date();return new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+1,1)).toISOString().slice(0,7)}""")
            expect(loc('planMonth')).to_have_value(month)
            loc('calculatePlan').click()
            expect(loc('planResult')).to_contain_text('Нет расходов')
            loc('planResult').get_by_role('button', name='Ввести расходы').click()
            def spend(index, category, amount):
                row = loc('spendRows').locator(':scope > div').nth(index)
                row.locator('[data-key=categoryId]').fill(category)
                row.locator('[data-key=amount]').fill(amount)
            spend(0, 'cafe', '1000')
            loc('spendingInputs').get_by_role('button', name='Добавить покупку').click()
            spend(1, 'supermarkets', '2000')
            loc('calculatePlan').click()
            expect(loc('planResult')).to_contain_text('Нет подтверждённых условий')
            banks = loc('bankId').locator('option').evaluate_all('(options) => options.slice(0,2).map(o=>[o.value,o.text])')
            assert len(banks) == 2
            labels = ['Кафе', 'Супермаркеты']
            for i, ((bank, _), label) in enumerate(zip(banks, labels)):
                loc('planResult').get_by_role('button', name='Добавить предложения банка').click()
                loc('bankId').select_option(bank)
                expect(loc('cashbackShot')).not_to_be_visible()
                loc('chooseOffer').click()
                loc('manualDraft').click()
                loc('reviewMonth').fill(month)
                loc('reviewSlots').fill('1')
                row = loc('reviewRows').locator('fieldset').first
                if not row.locator('details').get_attribute('open'):
                    row.locator('summary').click()
                row.locator('[data-key=label]').fill(label)
                row.locator('[data-key=rateBps]').fill('5' if not i else '10')
                row.locator('[data-key=include]').check()
                if not i:
                    loc('closeCatalog').click()
                    expect(loc('discardDialog')).to_be_visible()
                    loc('discardStay').click()
                    expect(row.locator('[data-key=label]')).to_have_value(label)
                loc('saveReview').click()
                expect(loc('catalogDialog')).to_be_hidden()
                loc('calculatePlan').click()
                expect(loc('planResult')).to_contain_text(label)
            def amounts():
                return loc('planResult').locator('[data-kopecks]').evaluate_all('(els)=>els.map(e=>Number(e.dataset.kopecks))')
            assert amounts() == [0, 25000, 25000], amounts()
            expect(loc('planResult')).to_contain_text('Ручной ввод')
            # Clear the in-memory offer details; the real planner returns labels, not full rules.
            page.on('dialog', lambda d: d.accept())
            page.reload()
            expect(loc('appScreen')).to_be_visible()
            page.evaluate("() => typeof walletRoute==='function' && walletRoute('home', true)")
            expect(loc('openPlan')).to_be_attached()
            loc('openPlan').click(force=True)
            loc('spendingSource').select_option('manual')
            spend(0, 'cafe', '1000')
            loc('spendingInputs').get_by_role('button', name='Добавить покупку').click()
            spend(1, 'supermarkets', '2000')
            loc('calculatePlan').click()
            for i, ((_, bank_name), label) in enumerate(zip(banks, labels)):
                group = loc('planResult').locator('article', has_text=bank_name)
                group.get_by_role('button', name='Я выбрал это в банке').click()
                expect(loc('reviewMonth')).to_have_value(month)
                row = loc('reviewRows').locator('fieldset').first
                expect(row.locator('[data-key=label]')).to_have_value(label)
                if not row.locator('details').get_attribute('open'):
                    row.locator('summary').click()
                rate = '5' if not i else '10'
                row.locator('[data-key=rateBps]').evaluate(
                    '(el, value) => { el.value = value; el.dispatchEvent(new Event("input", {bubbles: true})); }',
                    rate,
                )
                loc('reviewSlots').fill('1', force=True)
                row.locator('[data-key=include]').check()
                loc('saveReview').click()
                expect(loc('shotError')).to_be_empty()
                expect(loc('catalogDialog')).to_be_hidden()
                loc('calculatePlan').click()
                expect(loc('planResult').locator('article')).to_have_count(1-i)
            page.wait_for_function(
                """() => {
                  const values = [...document.querySelectorAll('#planResult [data-kopecks]')]
                    .map(node => Number(node.dataset.kopecks));
                  return values.length === 3 && values[0] === 25000 && values[1] === 25000 && values[2] === 0;
                }"""
            )
            assert amounts() == [25000, 25000, 0], amounts()
            loc('closePlan').click()
            expect(loc('openPlan')).to_be_focused()
            assert not errors and not blocked, (errors, blocked)
        finally:
            browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_url', nargs='?', default='http://127.0.0.1:8767')
    parser.add_argument('--chromium-executable')
    args = parser.parse_args()
    check(args.base_url.rstrip('/'), args.chromium_executable)
    print('Two-bank browser plan passed.')
