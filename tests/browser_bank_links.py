import json
import argparse
from urllib.parse import unquote, urlsplit
from playwright.sync_api import sync_playwright
parser = argparse.ArgumentParser()
parser.add_argument('base_url')
parser.add_argument('--chromium-executable')
args = parser.parse_args()
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=args.chromium_executable)
    page=browser.new_page(viewport={'width':390,'height':844})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(args.base_url.rstrip('/') + '/bank-link-test')
    direct = {'tbank://main', 'tinkoffbank://Main', 'wheels://Main'}
    sber = 'https://v.sber.ru/sms/forlifestyle?from=siteteaser'
    shortcuts = {f'shortcuts://run-shortcut?name={name}' for name in ('OpenSber', 'OpenTBank', 'OpenAlfa', 'OpenVTB')}
    page.locator('#platform').select_option('ios')
    ios_links = page.locator('.launch').evaluate_all('(xs) => xs.map(x => x.getAttribute("href"))')
    assert len(ios_links) == len(set(ios_links))
    assert direct | shortcuts | {sber} <= set(ios_links)
    assert page.locator('#shortcutHelp').is_visible()
    shortcut = page.get_by_role('link', name='Команда OpenSber')
    shortcut.evaluate('(a) => a.addEventListener("click", event => event.preventDefault())')
    shortcut.click()
    page.get_by_label('Результат: Команда OpenSber').select_option(label='Открылась главная банка')
    page.locator('#platform').select_option('android')
    android_links = page.locator('.launch').evaluate_all('(xs) => xs.map(x => x.getAttribute("href"))')
    assert set(url for url in android_links if not url.startswith('intent://')) == direct | {sber}
    assert not page.locator('#shortcutHelp').is_visible()
    links = [url for url in android_links if url.startswith('intent://')]
    assert len(links)==6
    for url in links:
        assert 'scheme=' in url and 'package=' in url
        assert 'S.browser_fallback_url=https%3A%2F%2F' in url
        assert url.endswith(';end')
    fallback_hosts = {urlsplit(unquote(url.split('S.browser_fallback_url=', 1)[1][:-4])).hostname for url in links}
    assert fallback_hosts == {'www.tbank.ru', 'online.sberbank.ru', 'web.alfabank.ru', 'online.vtb.ru'}
    official = page.get_by_role('link', name='Официальная ссылка Сбера')
    official.evaluate('(a) => a.addEventListener("click", event => event.preventDefault())')
    official.click()
    page.get_by_label('Результат: Официальная ссылка Сбера').select_option(label='Открылся сайт')
    page.reload()
    page.locator('#export').click()
    report=json.loads(page.locator('#report').input_value())
    assert len(report['records']) == 2
    assert report['records'][0]['url'] == 'shortcuts://run-shortcut?name=OpenSber'
    assert report['records'][0]['platform'] == 'ios'
    assert report['records'][1]['url'] == sber
    assert report['records'][1]['platform'] == 'android'
    assert report['records'][1]['result'] == 'Открылся сайт'
    assert not errors,errors
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    print('PASS: exact bank links, iOS shortcuts, Android intents and fallbacks, saved outcomes, mobile width. Device launches require a phone.')
    browser.close()
