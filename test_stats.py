import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from advisor import month_totals
from catalog import initialize
from test_cashback import API


class MonthTotals(unittest.TestCase):
    def test_recorded_choices_against_best_and_usual(self):
        totals = month_totals([
            dict(chosenKopecks=10000, recommendedKopecks=15000, usualKopecks=8000),
            dict(chosenKopecks=5000, recommendedKopecks=5000, usualKopecks=2000),
        ])
        self.assertEqual(totals['count'], 2)
        self.assertEqual(totals['calculatedKopecks'], 15000)
        self.assertEqual(totals['recommendedKopecks'], 20000)
        self.assertEqual(totals['missedKopecks'], 5000)
        self.assertEqual(totals['versusUsualKopecks'], 5000)

    def test_without_usual_card_the_gap_stays_empty(self):
        totals = month_totals([
            dict(chosenKopecks=10000, recommendedKopecks=10000, usualKopecks=None),
        ])
        self.assertIsNone(totals['usualKopecks'])
        self.assertIsNone(totals['versusUsualKopecks'])


class StatsMonthQuery(unittest.TestCase):
    def test_month_defaults_to_current_utc_and_filters_by_query(self):
        with tempfile.TemporaryDirectory() as folder, patch('advisor.datetime') as clock:
            clock.now.return_value = datetime(2026, 11, 20, tzinfo=UTC)
            path = Path(folder) / 'advisor.sqlite3'
            initialize(path)
            from advisor import create_app
            app = create_app(path)
            with API(app) as client, API(app) as stranger:
                self.assertEqual(stranger.get('/api/me/stats').status_code, 401)
                self.assertEqual(client.post('/api/auth/register', json={
                    'login': 'stats_month', 'password': 'test-only-long-password',
                }).status_code, 201)
                card = client.post('/api/me/manual-cards', json={
                    'name': 'Карта',
                    'rules': [{'categoryId': 'cafe', 'rateBps': 500, 'validFrom': '2026-01-01'}],
                }).json()['cardId']
                purchase = {'chosenCardId': card, 'categoryId': 'cafe', 'amountKopecks': 10000}
                self.assertEqual(client.post('/api/me/purchases', json={
                    **purchase, 'requestId': 'stats-month-nov-0001',
                }).status_code, 201)
                current = client.get('/api/me/stats').json()
                self.assertEqual(current['month'], '2026-11')
                self.assertEqual(current['count'], 1)
                november = client.get('/api/me/stats?month=2026-11').json()
                self.assertEqual(november['month'], '2026-11')
                self.assertEqual(november['count'], 1)
                october = client.get('/api/me/stats?month=2026-10').json()
                self.assertEqual(october['month'], '2026-10')
                self.assertEqual(october['count'], 0)
                self.assertEqual(client.get('/api/me/stats?month=2026-13').status_code, 422)
                self.assertEqual(client.get('/api/me/stats?month=bad').status_code, 422)
                self.assertEqual(stranger.post('/api/auth/register', json={
                    'login': 'stats_other', 'password': 'test-only-long-password',
                }).status_code, 201)
                other = stranger.get('/api/me/stats?month=2026-11').json()
                self.assertEqual(other['count'], 0)

    def test_actual_cashback_on_stats_and_purchase_endpoint(self):
        with tempfile.TemporaryDirectory() as folder, patch('advisor.datetime') as clock:
            clock.now.return_value = datetime(2026, 11, 20, tzinfo=UTC)
            path = Path(folder) / 'advisor.sqlite3'
            initialize(path)
            from advisor import create_app
            app = create_app(path)
            with API(app) as client, API(app) as other:
                self.assertEqual(client.post('/api/auth/register', json={
                    'login': 'cashback_ui', 'password': 'test-only-long-password',
                }).status_code, 201)
                self.assertEqual(other.post('/api/auth/register', json={
                    'login': 'cashback_other', 'password': 'test-only-long-password',
                }).status_code, 201)
                card = client.post('/api/me/manual-cards', json={
                    'name': 'Карта',
                    'rules': [{'categoryId': 'cafe', 'rateBps': 500}],
                }).json()['cardId']
                one = client.post('/api/me/purchases', json={
                    'chosenCardId': card, 'categoryId': 'cafe', 'amountKopecks': 10000,
                    'requestId': 'actual-cashback-one-01',
                }).json()['id']
                two = client.post('/api/me/purchases', json={
                    'chosenCardId': card, 'categoryId': 'cafe', 'amountKopecks': 20000,
                    'requestId': 'actual-cashback-two-02',
                }).json()['id']
                self.assertEqual(other.put(f'/api/me/purchases/{one}/cashback',
                                           json={'amountKopecks': 100}).status_code, 404)
                self.assertEqual(client.put(f'/api/me/purchases/{one}/cashback',
                                            json={'amountKopecks': 0}).status_code, 204)
                self.assertEqual(client.put(f'/api/me/purchases/{two}/cashback',
                                            json={'amountKopecks': 15000}).status_code, 204)
                report = client.get('/api/me/stats').json()
                self.assertEqual((report['actualCashbackKopecks'], report['actualCashbackCount']), (15000, 2))
                by_id = {row['id']: row['actualCashbackKopecks'] for row in report['purchases']}
                self.assertEqual(by_id, {one: 0, two: 15000})
                self.assertEqual(client.put(f'/api/me/purchases/{two}/cashback',
                                            json={'amountKopecks': None}).status_code, 204)
                report = client.get('/api/me/stats').json()
                self.assertEqual((report['actualCashbackKopecks'], report['actualCashbackCount']), (0, 1))
                by_id = {row['id']: row['actualCashbackKopecks'] for row in report['purchases']}
                self.assertEqual(by_id, {one: 0, two: None})
