import asyncio
import base64
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import httpx

from advisor import create_app, decode_image, parse_rules
from catalog import connect, initialize


class API:
    def __init__(self, app):
        self.loop = asyncio.new_event_loop()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')
        self.loop.run_until_complete(self.client.__aenter__())

    def _request(self, method, path, body):
        return self.loop.run_until_complete(self.client.request(method, path, json=body))

    def get(self, path):
        return self._request('GET', path, None)

    def post(self, path, json=None):
        return self._request('POST', path, json)

    def close(self):
        self.loop.run_until_complete(self.client.__aexit__(None, None, None))
        self.loop.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

MONTH = '2026-11'
IMAGE = 'data:image/jpeg;base64,' + base64.b64encode(b'\xff\xd8\xff' + b'x' * 40).decode()


def rule(label='Такси', cid='Такси', rate=500, **extra):
    return dict(dict(label=label, categoryId=cid, rateBps=rate, limitKopecks=None,
                     minAmountKopecks=1, selected=True, uncertain=False), **extra)


class Cashback(unittest.TestCase):
    def setUp(self):
        clock = self.enterContext(patch('advisor.datetime'))
        clock.now.return_value = datetime(2026, 11, 20, tzinfo=UTC)
        self.path = Path(self.enterContext(tempfile.TemporaryDirectory())) / 'test.db'
        initialize(self.path)
        self.app = create_app(self.path)
        self.client = API(self.app)
        self.addCleanup(self.client.close)
        self.login(self.client, 'owner')

    def login(self, client, login):
        self.assertEqual(client.post('/api/auth/register', json={'login': login, 'password': 'demo1234'}).status_code, 201)

    def confirm(self, key='first', rules=None, **fields):
        body = dict(bankId='sber', month=MONTH, mode='active', slots=3, requestId=key,
                    rules=[rule()] if rules is None else rules)
        return self.client.post('/api/me/cashback-confirm', json={**body, **fields})

    def test_draft_never_writes_and_keeps_distinct_labels(self):
        model = {'month': MONTH, 'rules': [dict(label=name, categoryId='transport', ratePercent=rate, selected=sel)
                                         for name, rate, sel in [('Такси', 5, True), ('Транспорт', 3, False), ('Метро', 4, None)]]}
        parsed = parse_rules(json.dumps(model))
        self.assertEqual([r['categoryId'] for r in parsed], ['Такси', 'transport', 'Метро'])
        self.assertEqual([r['selected'] for r in parsed], [True, False, None])
        with patch('advisor.read_cashback', return_value={'rules': parsed, 'month': MONTH}):
            resp = self.client.post('/api/me/cashback-screenshot', json={'bankId': 'sber', 'image': IMAGE})
        self.assertEqual(resp.json(), {'rules': parsed, 'month': MONTH})
        self.assertEqual(self.client.get('/api/me/manual-cards').json(), [])
        with self.assertRaises(ValueError):
            decode_image('data:text/plain;base64,YQ==')

    def test_merge_replay_and_rollback(self):
        first = self.confirm()
        self.assertIn(first.status_code, (200, 201), first.text)
        card = first.json()['cardId']
        second = self.confirm('two', [rule('Метро', 'Метро', 800), rule('Кино', 'Кино', selected=False)], cardId=card)
        self.assertIn(second.status_code, (200, 201), second.text)
        self.assertEqual(self.confirm().json(), first.json())
        self.assertEqual(self.confirm(rules=[rule(rate=100)]).status_code, 409)
        self.assertEqual(self.confirm('bad', [rule('Новая', 'Новая'), rule(rate=-1)], cardId=card).status_code, 422)
        with connect(self.path) as db:
            stored = db.execute('SELECT rules_json FROM cashback_sets').fetchall()
            self.assertEqual(len(stored), 1)
            self.assertEqual([r['label'] for r in json.loads(stored[0][0])], ['Такси', 'Метро'])

    def test_rules_current_period_exact_then_fallback_legacy_and_privacy(self):
        created = self.client.post('/api/me/manual-cards', json={'name': 'СберБанк', 'rules':[{'categoryId':'fuel','rateBps':50}]}).json()
        card = created['cardId']
        active = [rule(minAmountKopecks=10000), rule('Все покупки','all',1000)]
        self.assertIn(self.confirm(rules=active, cardId=card).status_code, (200,201))
        self.confirm('future', [rule('Февраль', 'Февраль')], month='2027-02', cardId=card)
        self.confirm('offer', [rule('Опция', 'Опция')], mode='offer', cardId=card)
        def rank(amount, cid):
            return self.client.post('/api/recommendations',json=dict(scope='mine',amountKopecks=amount,categoryId=cid)).json()['allMatches']
        self.assertEqual([r['cashbackKopecks'] for r in rank(10000, 'Такси')], [500])
        self.assertEqual([r['cashbackKopecks'] for r in rank(5000, 'Такси')], [500])
        self.assertEqual([r['cashbackKopecks'] for r in rank(10000, 'fuel')], [50])
        visible = self.client.get('/api/meta').json()['categories']
        self.assertIn('Такси',visible); self.assertNotIn('Опция',visible); self.assertNotIn('Февраль',visible)
        self.assertEqual({r['categoryId'] for r in self.client.get('/api/me/manual-cards').json()[0]['rules']},{'fuel','Такси','all'})
        with API(self.app) as other:
            self.login(other, 'stranger')
            self.assertNotIn('Такси', other.get('/api/meta').json()['categories'])
            with patch('advisor.read_cashback') as model:
                bad = other.post('/api/me/cashback-screenshot',json=dict(bankId='sber',cardId=card,image=IMAGE))
                self.assertEqual(bad.status_code,404); model.assert_not_called()
            self.assertEqual(other.post('/api/me/cashback-confirm',json=dict(bankId='sber',cardId=card,mode='active',month=MONTH,slots=1,requestId='x',rules=[rule()])).status_code,404)
        payload=dict(chosenCardId=card,categoryId='Такси',amountKopecks=10000,requestId='record-123')
        for _ in range(2):
            self.assertEqual(self.client.post('/api/me/purchases',json=payload).status_code,201)
        self.assertEqual(self.client.get('/api/me/stats').json()['count'],1)

    def test_ambiguous_bank_needs_card_id(self):
        for _ in range(2):
            self.client.post('/api/me/manual-cards',json=dict(name='СберБанк',rules=[]))
        self.assertEqual(self.confirm().status_code,409)
        self.assertEqual(len(self.client.get('/api/me/manual-cards').json()),2)

    def test_old_users_not_dropped(self):
        legacy=self.path.with_suffix('.legacy')
        with connect(legacy) as db:
            db.execute('CREATE TABLE users(session TEXT PRIMARY KEY, login TEXT UNIQUE, created_on TEXT)')
            db.execute("INSERT INTO users VALUES('old','old','2026-01-01')")
        initialize(legacy)
        with connect(legacy) as db:
            self.assertEqual(db.execute('SELECT login FROM users').fetchall(), [('old',)])

    def test_edit_rate_preserves_monthly_limit_and_never_changes_public_catalog(self):
        confirmed = self.confirm()
        card = confirmed.json()['cardId']
        limits = f'/api/me/cards/{card}/monthly'
        rates = f'/api/me/manual-cards/{card}/rate'
        config = {'limitKopecks': 5000, 'usedKopecks': 3500}
        rank = dict(scope='mine', amountKopecks=50000, categoryId='Такси')
        public = dict(scope='all', amountKopecks=250000, categoryId='supermarkets')
        old_catalog = self.client.post('/api/recommendations', public).json()
        self.assertEqual(self.client._request('PUT', limits, config).json()['remainingKopecks'], 1500)
        self.assertEqual(self.client.post('/api/recommendations', rank).json()['top3'][0]['cashbackKopecks'], 1500)
        change = {'categoryId': 'Такси', 'label': 'Такси', 'rateBps': 200}
        self.assertEqual(self.client._request('PATCH', rates, change).status_code, 204)
        self.assertEqual(self.client.post('/api/recommendations', rank).json()['top3'][0]['cashbackKopecks'], 1000)
        self.assertEqual(self.client.get(limits).json(), dict(month=MONTH, remainingKopecks=1500, **config))
        self.assertEqual(self.client.post('/api/recommendations', public).json(), old_catalog)
        with API(self.app) as other:
            self.login(other, 'another_owner')
            self.assertEqual(other.get(limits).status_code, 404)
            self.assertEqual(other._request('PATCH', rates, change).status_code, 404)
        self.assertEqual(self.client._request('PUT', limits, {**config, 'usedKopecks':5000}).status_code, 200)
        self.assertEqual(self.client.post('/api/recommendations', rank).json()['top3'][0]['cashbackKopecks'], 0)

    def test_wallet_journal_on_database_from_previous_release(self):
        legacy = self.path.with_suffix('.staging')
        with connect(legacy) as db:
            db.executescript('''
                CREATE TABLE purchases (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL, day TEXT NOT NULL,
                    category TEXT NOT NULL, merchant TEXT NOT NULL, amount INTEGER NOT NULL,
                    used_card TEXT, estimates TEXT NOT NULL
                );
                INSERT INTO purchases VALUES
                    ('classic-1','old-owner','2026-11-10','Еда','Магазин',60000,NULL,'{}');
            ''')
        initialize(legacy)
        with API(create_app(legacy)) as client:
            self.login(client, 'next_wallet')
            card = client.post('/api/me/manual-cards', json={
                'name': 'СберБанк', 'rules': [{'categoryId': 'fuel', 'rateBps': 400}],
            }).json()['cardId']
            purchase = client.post('/api/me/purchases', json={
                'chosenCardId': card, 'categoryId': 'fuel', 'amountKopecks': 25_000,
            })
            self.assertEqual(purchase.status_code, 201, purchase.text)
            self.assertEqual(client.get('/api/me/stats').json()['calculatedKopecks'], 1000)
            plan = client.post('/api/me/cashback-plan', json={'month': MONTH, 'spendingMonth': MONTH})
            self.assertEqual(plan.status_code, 200, plan.text)
        initialize(legacy)
        with connect(legacy) as db:
            self.assertEqual(db.execute('SELECT id, amount FROM purchases').fetchall(), [('classic-1', 60_000)])
            self.assertEqual(db.execute('SELECT amount_kopecks FROM wallet_purchases').fetchall(), [(25_000,)])
