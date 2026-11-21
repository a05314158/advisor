"""Capture UI screenshots for baseline or after comparison."""
import argparse
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import sync_playwright

WIDTHS = (320, 390, 430, 1280)

def _home(page, base):
    page.goto(base)
    page.frame_locator("#welcomeScreen").locator("#start").click()
    auth = page.locator("#authForm")
    login, password = "ui_" + uuid4().hex[:8], uuid4().hex
    auth.get_by_label("Логин").fill(login)
    auth.get_by_label("Пароль", exact=True).fill(password)
    page.get_by_role("button", name="Создать кошелёк").click()
    page.locator("#openBuy").wait_for()


def _cards_add(page, base):
    _home(page, base)
    page.locator("#openCards").click()
    page.locator("#openCatalog").click()
    page.locator("#addRouteBank").click()


def _buy(page, base):
    _home(page, base)
    page.locator("#openBuy").click()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("artifacts/ui-after"))
    parser.add_argument("--base", default="http://127.0.0.1:18745")
    args = parser.parse_args()
    args_base = args.base.rstrip("/")
    args.out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        shots = (
            ("home", lambda p: _home(p, args_base)),
            ("cards-add", lambda p: _cards_add(p, args_base)),
            ("buy", lambda p: _buy(p, args_base)),
            ("demo-fan", lambda p: p.goto(f"{args_base}/?demo=cards")),
        )
        for name, setup in shots:
            for w in WIDTHS:
                page = browser.new_page(viewport={"width": w, "height": 844}, locale="ru-RU")
                setup(page)
                page.wait_for_timeout(400)
                page.screenshot(path=args.out / f"{name}-{w}.png", full_page=True, animations="disabled")
                page.close()
        browser.close()
    print("Saved to", args.out.resolve())


if __name__ == "__main__":
    main()