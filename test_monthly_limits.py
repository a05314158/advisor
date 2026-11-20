import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from advisor import create_app


class MonthlyLimits(unittest.TestCase):
    def setUp(self):
        self.db = Path(self.enterContext(tempfile.TemporaryDirectory())) / 'test.sqlite3'
        self.clock = self.enterContext(patch('advisor.datetime'))
        self.clock.now.return_value = datetime(2026, 11, 30, 23, 59, tzinfo=UTC)
        self.client = self.enterContext(TestClient(create_app(self.db)))
        response = self.client.post('/api/me/manual-cards', json={'name':'Моя карта', 'rules':[
            {'categoryName':'Такси','rateBps':1000,'limitKopecks':20000},
            {'categoryName':'Кафе','rateBps':1000}]})
        self.assertEqual(response.status_code, 201)
        self.path = f"/api/me/manual-cards/{response.json()['cardId']}/monthly-limit"

    def update(self, used, month='2026-11', client=None):
        return (client or self.client).put(self.path, json=dict(month=month, limitKopecks=300000, usedKopecks=used))

    def ranking(self, category):
        response = self.client.post('/api/recommendations', json=dict(scope='manual', categoryId=category, amountKopecks=250000))
        self.assertEqual(response.status_code, 200)
        return response.json()['allMatches']

    def test_shared_remainder_read_only_calculation_and_month_rollover(self):
        self.assertEqual(self.update(290000).status_code, 204)
        for category in ('Такси', 'Кафе', 'Такси'):
            match, = self.ranking(category)
            self.assertEqual(match['cashbackKopecks'], 10000)
            self.assertTrue(match['monthlyLimitApplied'])
        self.assertEqual(self.update(300100).status_code, 204)
        self.assertEqual(self.ranking('Кафе'), [])
        self.clock.now.return_value = datetime(2026, 12, 1, tzinfo=UTC)
        self.assertEqual(self.update(300000).status_code, 409)
        card, = self.client.get('/api/me/manual-cards').json()
        self.assertEqual(card['monthly'], dict(month='2026-12', limitKopecks=300000, usedKopecks=0, remainingKopecks=300000))
        self.assertEqual(self.ranking('Такси')[0]['cashbackKopecks'], 20000)

    def test_owner_and_valid_amount(self):
        self.assertEqual(self.update(10000).status_code, 204)
        self.assertEqual(self.update(-1).status_code, 422)
        with TestClient(create_app(self.db)) as stranger:
            self.assertEqual(self.update(300000, client=stranger).status_code, 404)
        self.assertEqual(self.client.get('/api/me/manual-cards').json()[0]['monthly']['usedKopecks'], 10000)

    def test_monthly_usage_transfers_to_account_and_survives_reopen(self):
        self.assertEqual(self.update(290000).status_code, 204)
        credentials = dict(username='monthly.test', password='test-only-long-password')
        self.assertEqual(self.client.post('/api/auth/register', json=dict(**credentials, transferGuestCards=True)).status_code, 201)
        with TestClient(create_app(self.db)) as second:
            self.assertEqual(second.post('/api/auth/login', json=credentials).status_code, 200)
            self.assertEqual(second.get('/api/me/manual-cards').json()[0]['monthly']['remainingKopecks'], 10000)
