from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from fastapi.testclient import TestClient

from advisor import create_app


class PurchasePlanTests(TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.app = create_app(Path(directory) / 'plan.sqlite3')
        self.client = self.enterContext(TestClient(self.app))
        self.purchases = [
            dict(categoryId='supermarkets', amountKopecks=100_000),
            dict(categoryId='transport', amountKopecks=100_000),
        ]

    def add_card(self, name, supermarket, transport):
        response = self.client.post('/api/me/manual-cards', json=dict(name=name, rules=[
            dict(categoryId='supermarkets', rateBps=supermarket),
            dict(categoryId='transport', rateBps=transport),
        ]))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['cardId']

    def test_reserves_the_shared_cap_for_the_purchase_that_benefits_most(self):
        response = self.client.post('/api/auth/register', json=dict(login='plan_user', password='test-long-password'))
        self.assertEqual(response.status_code, 201, response.text)
        first = self.add_card('А', 1000, 1000)
        second = self.add_card('Б', 800, 100)
        limit = f'/api/me/cards/{first}/monthly'
        response = self.client.put(limit, json=dict(limitKopecks=30_000, usedKopecks=20_000))
        self.assertEqual(response.status_code, 200, response.text)

        response = self.client.post('/api/me/purchase-plan', json=dict(purchases=self.purchases))
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result['optimized']['totalKopecks'], 18_000)
        self.assertEqual(result['sequential']['totalKopecks'], 11_000)
        self.assertEqual(result['gainKopecks'], 7_000)
        reason = result['explanation']
        self.assertEqual(reason['code'], 'shared_limit')
        self.assertEqual(reason['cardId'], first)
        self.assertEqual((reason['reserveFromPurchaseIndex'], reason['useAtPurchaseIndex']), (0, 1))
        self.assertEqual([change['deltaKopecks'] for change in reason['changes']], [-2_000, 9_000])
        self.assertEqual([row['cardId'] for row in result['optimized']['purchases']], [second, first])
        self.assertEqual(self.client.get(limit).json()['usedKopecks'], 20_000)
        self.assertEqual(self.client.get('/api/me/stats').json()['count'], 0)

        response = self.client.put(limit, json=dict(limitKopecks=10_000, usedKopecks=None))
        self.assertEqual(response.status_code, 200, response.text)
        result = self.client.post('/api/me/purchase-plan', json=dict(purchases=self.purchases)).json()
        self.assertEqual(result['assumedFullCardIds'], [first])
        self.assertEqual(result['assumedFullCards'], [dict(cardId=first, cardName='А')])

        with TestClient(self.app) as other:
            result = other.post('/api/me/purchase-plan', json=dict(purchases=self.purchases)).json()
            self.assertEqual(result['optimized']['totalKopecks'], 0)
            self.assertEqual(result['explanation'], dict(code='same_total', changes=[]))
            self.assertEqual([entry['cardId'] for entry in result['optimized']['purchases']], [None, None])

    def test_validates_count_category_and_amount(self):
        for purchases in [[], self.purchases[:1], self.purchases * 5,
                          [self.purchases[0], dict(categoryId='missing', amountKopecks=1)],
                          [self.purchases[0], dict(categoryId='cafe', amountKopecks=True)]]:
            with self.subTest(purchases=purchases):
                response = self.client.post('/api/me/purchase-plan', json=dict(purchases=purchases))
                self.assertEqual(response.status_code, 422, response.text)
