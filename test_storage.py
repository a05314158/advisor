import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, UTC
from pathlib import Path

from fastapi.testclient import TestClient

from advisor import create_app
from catalog import import_catalog, SEED


class StorageTests(unittest.TestCase):
    def test_manual_only_matches_custom_categories_across_many_cards(self):
        with TestClient(create_app(self.db)) as client:
            self.assertEqual(client.put('/api/me/cards/A').status_code, 204)
            query = dict(categoryId='  ТАКСИ ', amountKopecks=10000, scope='manual')
            self.assertEqual(client.post('/api/recommendations', json=query).json()['allMatches'], [])
            for i in range(7):
                rules = [dict(categoryName='Такси', rateBps=100+i)]
                rules += [dict(categoryName=f'Категория {j}', rateBps=500) for j in range(i)]
                self.assertEqual(client.post('/api/me/manual-cards', json=dict(name=f'Моя {i}', rules=rules)).status_code, 201)
            cards = client.get('/api/me/manual-cards').json()
            self.assertEqual([len(c['rules']) for c in cards], list(range(1, 8)))
            result = client.post('/api/recommendations', json=query).json()
            self.assertEqual([c['cashbackKopecks'] for c in result['allMatches']], list(range(106, 99, -1)))
            self.assertEqual(client.post('/api/recommendations', json=dict(query, categoryId='Супермаркеты')).json()['allMatches'], [])
            duplicate = [dict(categoryName=n, rateBps=500) for n in ('Такси', ' такси ')]
            self.assertEqual(client.post('/api/me/manual-cards', json=dict(name='Дубль', rules=duplicate)).status_code, 422)

    def test_manual_card_is_private_and_calculated(self):
        payload = {'name': 'Моя карта', 'rules': [{'categoryId': 'cafe', 'rateBps': 1000, 'limitKopecks': 12000},
                                                  {'categoryId': 'fuel', 'rateBps': 500}]}
        query = dict(categoryId='cafe', amountKopecks=250000, scope='mine')
        with TestClient(create_app(self.db)) as client:
            result = client.post('/api/me/manual-cards', json=payload)
            self.assertEqual(result.status_code, 201)
            self.assertEqual(client.post('/api/me/manual-cards', json=dict(payload, rules=payload['rules'] * 2)).status_code, 422)
            card = result.json()['cardId']
            cookies = dict(client.cookies)
        with TestClient(create_app(self.db)) as client:
            self.assertEqual(client.get('/api/me/manual-cards').json(), [])
            client.cookies.update(cookies)
            self.assertEqual(len(client.get('/api/me/manual-cards').json()[0]['rules']), 2)
            match, = client.post('/api/recommendations', json=query).json()['top3']
            self.assertEqual((match['cardName'], match['cashbackKopecks']), ('Моя карта', 12000))
            fuel, = client.post('/api/recommendations', json=dict(query, categoryId='fuel')).json()['top3']
            self.assertEqual(fuel['cashbackKopecks'], 12500)
            self.assertNotIn(card, [x['cardId'] for x in client.post('/api/recommendations', json=dict(query, scope='all')).json()['allMatches']])
            self.assertEqual(client.delete(f'/api/me/manual-cards/{card}').status_code, 204)
            self.assertEqual(client.post('/api/recommendations', json=query).json()['top3'], [])

    def setUp(self):
        self.db = Path(self.enterContext(tempfile.TemporaryDirectory())) / 'test.db'
        self.enterContext(patch('advisor.datetime')).now.return_value = datetime(2026, 11, 20, tzinfo=UTC)

    def test_import_is_idempotent_and_conflicts_roll_back(self):
        import_catalog(self.db, SEED)
        import_catalog(self.db, SEED)
        with TestClient(create_app(self.db)) as client:
            before = client.get('/api/cards').json()
            self.assertEqual(sum(len(c['rules']) for c in before), 5)
            invalid = dict(SEED[0], validFrom='2026-11-02')
            with self.assertRaises(ValueError):
                import_catalog(self.db, [dict(SEED[0], rateBps=1), invalid])
            self.assertEqual(client.get('/api/cards').json(), before)
            import_catalog(self.db, [dict(SEED[0], rateBps=900)])
            self.assertEqual(client.get('/api/cards/A').json()['rules'][0]['rateBps'], 900)

    def test_saved_cards_survive_restart_and_are_isolated(self):
        with TestClient(create_app(self.db)) as first:
            for card in ('A', 'C', 'A'):
                self.assertEqual(first.put(f'/api/me/cards/{card}').status_code, 204)
            cookies = dict(first.cookies)
        with TestClient(create_app(self.db)) as second:
            self.assertEqual(second.get('/api/me/cards').json(), [])
            self.assertEqual(second.post('/api/recommendations', json=dict(categoryId='supermarkets', amountKopecks=250000, scope='mine')).json()['top3'], [])
            second.cookies.update(cookies)
            self.assertEqual(second.get('/api/me/cards').json(), ['A', 'C'])
            response = second.post('/api/recommendations', json=dict(categoryId='supermarkets', amountKopecks=250000, scope='mine'))
            self.assertEqual([c['cardId'] for c in response.json()['top3']], ['A', 'C'])
            self.assertEqual(second.delete('/api/me/cards/A').status_code, 204)
            self.assertEqual(second.get('/api/me/cards').json(), ['C'])
            self.assertEqual(second.put('/api/me/cards/Z').status_code, 404)
