import json
import argparse
from urllib.parse import unquote
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
    assert page.locator('.launch').count()==8
    assert page.locator('.launch').first.get_attribute('href')=='tinkoffbank://Main'
    page.locator('#platform').select_option('android')
    links=page.locator('.launch').evaluate_all('(xs)=>xs.map(x=>x.getAttribute("href"))')
    assert len(links)==6
    for url in links:
        assert 'scheme=' in url and 'package=' in url
        assert 'S.browser_fallback_url=https%3A%2F%2F' in url
        assert url.endswith(';end')
    page.locator('.launch').first.evaluate('(a)=>a.addEventListener("click",e=>e.preventDefault())')
    page.locator('.launch').first.click()
    page.locator('select[aria-label]').first.select_option(label='Открылся сайт')
    page.locator('#export').click()
    report=json.loads(page.locator('#report').input_value())
    assert len(report['records'])==1
    assert report['records'][0]['app']=='CraftT'
    assert report['records'][0]['result']=='Открылся сайт'
    assert not errors,errors
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    print('PASS: iOS/Android rendering, 6 Android intents and HTTPS fallbacks, explicit outcome recording, JSON export, mobile width. External app opening was NOT tested.')
    browser.close()
