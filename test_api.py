import unittest
import tempfile
from pathlib import Path
from datetime import UTC, datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from advisor import create_app


class RecommendationsAPI(unittest.TestCase):
    def setUp(self):
        clock = self.enterContext(patch('advisor.datetime'))
        clock.now.return_value = datetime(2026, 11, 20, tzinfo=UTC)
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.client = self.enterContext(TestClient(create_app(Path(directory) / 'test.db')))

    def request(self, **overrides):
        payload = dict(categoryId='supermarkets', amountKopecks=250000, scope='all')
        payload.update(overrides)
        return self.client.post('/api/recommendations', json=payload)

    def test_screen_is_served(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response.headers['content-type'])
        self.assertIn('/api/recommendations', response.text)

    def test_ranking_details_and_repeatability(self):
        response = self.request()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['asOf'], '2026-11-20')
        self.assertEqual(data['catalogVersion'], 'training-v1')
        self.assertEqual([(x['cardId'], x['cashbackKopecks']) for x in data['top3']],
                         [('B', 15000), ('A', 10000), ('C', 10000)])
        self.assertEqual([x['cardId'] for x in data['allMatches']], ['B', 'A', 'C', 'D'])
        capped = data['top3'][1]
        self.assertTrue(capped['limitApplied'])
        self.assertEqual(capped['limitKopecks'], 10000)
        self.assertEqual(capped['updatedOn'], '2026-11-01')
        self.assertEqual(self.request().json(), data)

    def test_cafe_changes_winner(self):
        response = self.request(categoryId='cafe')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([(x['cardId'], x['cashbackKopecks']) for x in response.json()['top3']],
                         [('D', 20000)])

    def test_empty_category_is_not_an_error(self):
        response = self.request(categoryId='fuel')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['top3'], [])
        self.assertEqual(response.json()['allMatches'], [])

    def test_invalid_amounts(self):
        for amount in (0, -1, 2.5, True, '250000', None):
            with self.subTest(amount=amount):
                response = self.request(amountKopecks=amount)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json(),
                                 {'field': 'amountKopecks', 'code': 'positive_integer_required'})

    def test_unknown_category(self):
        response = self.request(categoryId='unknown')
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['field'], 'categoryId')

    def test_empty_mine_does_not_show_all_cards(self):
        response = self.request(scope='mine')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['allMatches'], [])
