import unittest
from pathlib import Path


PAGE = Path(__file__).with_name('wallet.html').read_text(encoding='utf-8')
# Reference silhouette from the original wallet artwork; no external file is required.
POCKET = 'M43 72 Q45 51 68 51 Q192 43 322 57 Q346 59 347 82 L343 210 Q342 251 304 256 Q190 267 80 252 Q44 247 41 213 Q37 146 43 72Z'


class WalletPage(unittest.TestCase):
    def test_page_has_one_svg(self):
        self.assertEqual(PAGE.count('viewBox="0 0 390 330"'), 1)
        self.assertEqual(PAGE.count('id="pocket"'), 1)

    def test_old_drawn_wallet_is_gone(self):
        self.assertNotIn('650 840', PAGE)
        self.assertNotIn('leatherBody', PAGE)
        self.assertNotIn('pocket.webp', PAGE)
        self.assertNotIn('id="lining"', PAGE)

    def test_leather_file_is_the_wallet(self):
        self.assertIn(f'<path id="pocket" d="{POCKET}"/>', PAGE)
        self.assertLess(PAGE.index('id="pocketCards"'), PAGE.index('class="front"'))

    def test_hero_tags_balance(self):
        hero = PAGE.split('<section class="hero', 1)[1].split('</section>', 1)[0]
        self.assertEqual(hero.count('<div'), hero.count('</div>'))
        self.assertEqual(hero.count('<svg'), hero.count('</svg>'))

    def test_empty_line_is_inside_the_leather_wallet(self):
        wallet = PAGE.split('<div class="wallet">', 1)[1].split('</div>', 1)[0]
        self.assertIn('id="pocketEmpty"', wallet)
        self.assertIn('id="pocket"', wallet)

    def test_refresh_and_logout_are_gone(self):
        self.assertNotIn('id="refresh"', PAGE)
        self.assertNotIn('id="logout"', PAGE)

    def test_gallery_pick_reads_bytes(self):
        self.assertIn('accept="image/*"', PAGE)
        self.assertNotIn('readAsDataURL', PAGE)
        self.assertIn('file.slice', PAGE)

    def test_app_starts_hidden_behind_welcome(self):
        self.assertIn('id="appScreen" hidden', PAGE)
        self.assertIn('id="welcomeScreen"', PAGE)

    def test_home_is_purchase_and_cards(self):
        self.assertIn('aria-label="Тема"', PAGE)
        self.assertIn('aria-label="Настройки"', PAGE)
        self.assertNotIn('>Тёмная<', PAGE)
        self.assertIn('id="openBuy"', PAGE)
        self.assertIn('id="openCards"', PAGE)
        self.assertIn('id="buyAmount"', PAGE)
        self.assertIn('id="showStatsBtn"', PAGE)
        self.assertIn('id="openPlan"', PAGE)
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
        self.assertIn('carouselPoses=[[0,0,0,1,0,0],[1,1,.10,.77,4,16]', PAGE)

    def test_card_arc_keeps_empty_state_and_bank_colors(self):
        self.assertIn('Кошелёк пуст.', PAGE)
        self.assertIn('carouselCardPaint', PAGE)
        self.assertIn('--carousel-glow', PAGE)
        self.assertIn('card.rules||[]', PAGE)
