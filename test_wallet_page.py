import unittest
from pathlib import Path


PAGE = Path(__file__).with_name('wallet.html').read_text(encoding='utf-8')
# Reference silhouette from the original wallet artwork; no external file is required.
POCKET = 'M43 72 Q45 51 68 51 Q192 43 322 57 Q346 59 347 82 L343 210 Q342 251 304 256 Q190 267 80 252 Q44 247 41 213 Q37 146 43 72Z'


class WalletPage(unittest.TestCase):
    def test_page_has_one_svg(self):
        self.assertNotIn('viewBox="0 0 390 330"', PAGE)
        self.assertNotIn('id="pocket"', PAGE)
        self.assertIn('id="homePreview"', PAGE)

    def test_old_drawn_wallet_is_gone(self):
        self.assertNotIn('650 840', PAGE)
        self.assertNotIn('leatherBody', PAGE)
        self.assertNotIn('pocket.webp', PAGE)
        self.assertNotIn('id="lining"', PAGE)
        self.assertNotIn('wallet-nav', PAGE)

    def test_home_asks_before_the_cards(self):
        self.assertLess(PAGE.index('Какой картой выгоднее заплатить?'), PAGE.index('id="homePreview"'))
        self.assertLess(PAGE.index('id="openBuy"'), PAGE.index('id="openCards"'))
        self.assertIn('id="openPlan"', PAGE)
        self.assertIn('id="homeOffersStub"', PAGE)
        self.assertIn('id="accountPanel"', PAGE)

    def test_hero_tags_balance(self):
        hero = PAGE.split('<section class="hero', 1)[1].split('</section>', 1)[0]
        self.assertEqual(hero.count('<div'), hero.count('</div>'))
        self.assertEqual(hero.count('<svg'), hero.count('</svg>'))

    def test_empty_line_is_inside_the_leather_wallet(self):
        self.assertIn('id="homeSummary"', PAGE)
        self.assertIn('id="emptyAdd"', PAGE)
        self.assertIn('id="homeSummaryHint"', PAGE)
        self.assertIn('Добавьте карту', PAGE)

    def test_settings_controls_real_session_and_theme(self):
        self.assertIn('id="logout"', PAGE)
        self.assertIn('id="settingsTheme"', PAGE)
        self.assertIn('id="passwordToggle"', PAGE)

    def test_wallet_has_visible_routes_and_bank_search(self):
        self.assertNotIn('aria-label="Разделы кошелька"', PAGE)
        for key in ('historyPanel', 'buyPanel', 'cardsPanel', 'accountPanel'):
            self.assertIn(f'id="{key}"', PAGE)
        for key in ('historyPanel', 'bankSearch', 'addSource', 'deleteDialog'):
            self.assertIn(f'id="{key}"', PAGE)
        self.assertNotIn("String(index+1).padStart(4,'0')", PAGE)
        self.assertIn('Какой картой выгоднее заплатить?', PAGE)
        self.assertIn('>Сравнить карты<', PAGE)
        self.assertIn('src="/static/wallet-shell.js"', PAGE)
        self.assertIn('href="/static/wallet-shell.css"', PAGE)

    def test_gallery_pick_reads_bytes(self):
        self.assertIn('accept="image/*"', PAGE)
        self.assertNotIn('readAsDataURL', PAGE)
        self.assertIn('file.slice', PAGE)

    def test_app_starts_hidden_behind_welcome(self):
        self.assertIn('id="appScreen" hidden', PAGE)
        self.assertIn('id="welcomeScreen"', PAGE)

    def test_home_is_purchase_and_cards(self):
        self.assertIn('id="settingsTheme"', PAGE)
        self.assertIn('aria-label="Профиль"', PAGE)
        self.assertNotIn('>Тёмная<', PAGE)
        self.assertIn('id="openBuy"', PAGE)
        self.assertIn('id="openCards"', PAGE)
        self.assertIn('id="buyAmount"', PAGE)
        self.assertIn('id="showStatsBtn"', PAGE)
        self.assertIn('id="openPlan"', PAGE)
        self.assertIn('id="homeOffersStub"', PAGE)
        self.assertIn('src="/wallet-cashback.js"', PAGE)
        self.assertIn("defineProperty(window,name", PAGE)

    def test_card_arc_uses_pointer_swipe_and_keyboard(self):
        self.assertIn('id="cardCarousel"', PAGE)
        self.assertIn('touch-action:pan-y', PAGE)
        self.assertIn('pointerdown', PAGE)
        self.assertIn('pointermove', PAGE)
        self.assertIn('setPointerCapture', PAGE)
        self.assertIn('carouselPos.value=carouselPos.pos0-', PAGE)
        self.assertIn('ArrowLeft', PAGE)
        self.assertIn('ArrowRight', PAGE)
        self.assertIn('cubicBezier', PAGE)
        self.assertIn('prefers-reduced-motion: reduce', PAGE)
        self.assertIn('carouselPoses=[[0,0,0,1,0,0],[1,.94,.06,.93,10,2]', PAGE)
        self.assertIn('id="demoBar"', PAGE)
        self.assertIn('demo=cards', PAGE)
        self.assertIn('из ${cards.length}', PAGE)

    def test_card_arc_keeps_empty_state_and_bank_colors(self):
        self.assertIn('Кошелёк пуст.', PAGE)
        self.assertIn('carouselCardPaint', PAGE)
        self.assertIn('--carousel-glow', PAGE)
        self.assertIn('card.rules||[]', PAGE)
