import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from advisor import create_app


class WalletAPI(unittest.TestCase):
    def test_screenshot_uses_shared_account_and_preserves_monthly_limit(self):
        image = 'data:image/jpeg;base64,' + base64.b64encode(b'\xff\xd8\xff' + b'x' * 40).decode()
        with tempfile.TemporaryDirectory() as folder, TestClient(create_app(Path(folder) / 'db')) as client:
            body = {'bankId': 'tbank', 'image': image}
            self.assertEqual(client.post('/api/me/cashback-screenshot', json=body).status_code, 401)
            self.assertEqual(client.post('/api/auth/register', json={
                'username': 'wallet.test', 'password': 'test-only-long-password'}).status_code, 201)
            created = client.post('/api/me/manual-cards', json={
                'name': 'Т-Банк', 'rules': [], 'monthlyLimitKopecks': 10000})
            self.assertEqual(created.status_code, 201)
            card = created.json()['cardId']
            rules = [{'categoryId': 'supermarkets', 'rateBps': 500, 'limitKopecks': None}]
            with patch('advisor.read_cashback', return_value=rules):
                self.assertEqual(client.post('/api/me/cashback-screenshot', json={**body, 'cardId': card}).status_code, 201)
                self.assertEqual(client.post('/api/me/cashback-screenshot', json={**body, 'cardId': 'foreign'}).status_code, 404)
            cards = client.get('/api/me/manual-cards').json()
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0]['monthly']['limitKopecks'], 10000)
            response = client.post('/api/recommendations', json={
                'scope': 'mine', 'categoryId': 'supermarkets', 'amountKopecks': 250000})
            self.assertEqual(response.json()['top3'][0]['cashbackKopecks'], 10000)
