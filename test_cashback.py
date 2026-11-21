import base64
import unittest

from catalog import BANKS
from advisor import decode_image, parse_rules


class CashbackScreenshot(unittest.TestCase):
    def test_banks_replace_the_letter_cards(self):
        self.assertEqual(len(BANKS), 20)
        self.assertEqual(BANKS[0][1], 'СберБанк')
        self.assertEqual(BANKS[6][4], '#FFDD2D')
        self.assertEqual(BANKS[9][3], '#161616')
        self.assertTrue(all(bank[0].isascii() and bank[0].isalnum() for bank in BANKS))

    def test_visible_categories_become_rules(self):
        text = '''Вот что видно:
        {"rules":[
          {"categoryId":"supermarkets","ratePercent":5},
          {"categoryId":"unknown","ratePercent":9},
          {"categoryId":"cafe","ratePercent":1.5,"limitRub":3000},
          {"categoryId":"cafe","ratePercent":1}
        ]}'''
        self.assertEqual(parse_rules(text), [
            {'categoryId': 'supermarkets', 'rateBps': 500, 'limitKopecks': None},
            {'categoryId': 'cafe', 'rateBps': 150, 'limitKopecks': 300000},
        ])

    def test_sber_screen_words(self):
        text = '''{"rules":[
          {"categoryId":"На все покупки","ratePercent":"1%"},
          {"categoryId":"Кино и театр","ratePercent":"5%"},
          {"categoryId":"Такси","ratePercent":"3%"},
          {"categoryId":"Транспорт","ratePercent":"15%"},
          {"categoryId":"Фастфуд","ratePercent":"4%"}
        ]}'''
        rules = {rule['categoryId']: rule['rateBps'] for rule in parse_rules(text)}
        self.assertEqual(rules, {'fast_food': 400, 'taxi': 300, 'transport': 1500, 'entertainment': 500, 'all': 100})

    def test_words_and_percent_signs(self):
        text = '{"rules":[{"categoryId":"Супермаркеты","ratePercent":"5%","limitRub":"без лимита"},{"categoryId":"cafe","ratePercent":"1,5","limitRub":"3 000"}]}'
        self.assertEqual(parse_rules(text), [
            {'categoryId': 'supermarkets', 'rateBps': 500, 'limitKopecks': None},
            {'categoryId': 'cafe', 'rateBps': 150, 'limitKopecks': 300000},
        ])

    def test_screenshot_must_be_an_image(self):
        blob = b'\xff\xd8\xff' + b'x' * 40
        image = 'data:image/jpeg;base64,' + base64.b64encode(blob).decode()
        self.assertTrue(decode_image(image).startswith('data:image/jpeg;base64,'))
        with self.assertRaises(ValueError):
            decode_image('data:text/plain;base64,YQ==')
