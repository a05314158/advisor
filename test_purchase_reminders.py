import base64
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from advisor import create_app
from purchase_reminders import deliver_due, send_web_push


class PurchaseReminders(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.db = Path(folder) / 'reminders.sqlite3'
        self.moment = datetime.now(UTC)
        self.enterContext(patch('purchase_reminders.now_utc', return_value=self.moment))
        app = create_app(self.db)
        self.client = self.enterContext(TestClient(app))
        self.other = self.enterContext(TestClient(app))
        for actor, name in ((self.client, 'push_owner'), (self.other, 'push_other')):
            self.assertEqual(actor.post('/api/auth/register', json={
                'login': name, 'password': 'test-password',
            }).status_code, 201)
        self.card = self.add_card('Карта 5%', 500)
        self.backup = self.add_card('Карта 3%', 300)

    def add_card(self, name, rate):
        response = self.client.post('/api/me/manual-cards', json={
            'name': name, 'rules': [{'categoryId': 'cafe', 'rateBps': rate}],
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['cardId']

    def create(self, **kwargs):
        payload = dict(categoryId='cafe', amountKopecks=10_000, chosenCardId=self.card,
                       requestId=str(uuid4()), timezone='UTC')
        payload.update(kwargs)
        response = self.client.post('/api/me/purchase-drafts', json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    @staticmethod
    def path(draft):
        return '/api/me/purchase-drafts/' + draft['id']

    def test_create_is_explicit_and_idempotent_and_account_isolated(self):
        self.client.post('/api/recommendations', json={'categoryId': 'cafe', 'amountKopecks': 10_000, 'scope': 'mine'})
        self.assertEqual(self.client.get('/api/me/purchase-drafts').json(), {'drafts': []})
        retry_key = str(uuid4())
        draft = self.create(requestId=retry_key)
        self.assertEqual(self.create(requestId=retry_key), draft)
        self.assertEqual(self.client.post('/api/me/purchase-drafts', json={
            'requestId': retry_key, 'categoryId': 'cafe', 'amountKopecks': 11_000, 'chosenCardId': self.card,
        }).status_code, 409)
        self.assertEqual(self.other.get(self.path(draft)).status_code, 404)
        self.assertEqual(self.other.put(self.path(draft) + '/decision', json={'action': 'confirm'}).status_code, 404)
        self.assertEqual(self.other.get('/api/me/purchase-drafts').json(), {'drafts': []})
        self.assertEqual(self.client.get('/api/me/stats').json()['count'], 0)
        self.assertEqual(self.client.get('/api/me/push').json(), {'publicKey': None})

    def test_parallel_confirm_uses_snapshot_once_and_decline_writes_nothing(self):
        draft = self.create()
        declined = self.create()
        path = self.path(draft) + '/decision'
        with ThreadPoolExecutor(4) as pool:
            responses = list(pool.map(lambda _: self.client.put(path, json={
                'action': 'confirm', 'chosenCardId': self.backup, 'amountKopecks': 20_000,
            }), range(4)))
        self.assertTrue(all(response.status_code == 200 for response in responses))
        self.assertEqual(len({response.json()['purchaseId'] for response in responses}), 1)
        self.assertEqual(self.client.put(path, json={'action': 'decline'}).status_code, 409)
        self.assertEqual(self.client.put(self.path(declined) + '/decision', json={'action': 'decline'}).json()['status'], 'declined')
        self.assertEqual(self.client.get(self.path(declined)).json()['status'], 'declined')
        stats = self.client.get('/api/me/stats').json()
        self.assertEqual(stats['count'], 1)
        self.assertEqual(stats['purchases'][0]['cardId'], self.backup)
        self.assertEqual(stats['purchases'][0]['chosenKopecks'], 600)
        self.assertIsNone(stats['purchases'][0]['actualCashbackKopecks'])
        self.assertEqual(self.client.get('/api/me/purchase-drafts').json()['drafts'], [])

    def test_changed_payment_month_without_historical_estimates(self):
        draft = self.create()
        prior = (self.moment.date().replace(day=1) - timedelta(days=1)).isoformat()
        path = self.path(draft) + '/decision'
        self.assertEqual(self.client.put(path, json={'action': 'confirm', 'paidOn': '2099-01-01'}).status_code, 422)
        result = self.client.put(path, json={'action': 'confirm', 'paidOn': prior})
        self.assertEqual(result.json()['paidOn'], prior)
        self.assertEqual(self.client.get('/api/me/stats').json()['count'], 0)
        purchase = self.client.get('/api/me/stats?month=' + prior[:7]).json()['purchases'][0]
        self.assertEqual(purchase['date'], prior)
        self.assertFalse(purchase['estimateAvailable'])
        self.assertIsNone(purchase['actualCashbackKopecks'])

    def test_push_is_opt_in_scheduled_and_claimed_once(self):
        draft = self.create(timezone='Europe/Moscow')
        closed = self.create(timezone='Europe/Moscow')
        self.client.put(self.path(closed) + '/decision', json={'action': 'decline'})
        due = datetime.fromisoformat(draft['remindAt'])
        self.assertEqual(due.hour, 9)
        self.assertEqual(due.date().isoformat(), (datetime.fromisoformat(draft['paidOn']).date() + timedelta(days=1)).isoformat())
        with patch('purchase_reminders.settings', return_value=('public', 'private', 'mailto:push@example.test')):
            encode = lambda key: base64.urlsafe_b64encode(key).decode().rstrip('=')
            sub = {'endpoint': 'https://fcm.googleapis.com/fcm/send/demo', 'keys': {
                'p256dh': encode(b'\x04' + b'\xff' * 64), 'auth': encode(b'\xad' * 16),
            }}
            calls = []

            def send(subscription, draft_id):
                calls.append((subscription, draft_id))
                return False  # A provider reported an expired device.

            deliver_due(self.db, send, now=due)
            self.assertEqual(calls, [])
            response = self.client.put('/api/me/push', json={**sub, 'endpoint': 'https://fcm.googleapis.com@example.test/a'})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(self.client.put('/api/me/push', json=sub).status_code, 204)
            self.assertTrue(self.client.post('/api/me/push/status', json=sub).json()['enabled'])
            self.assertFalse(self.other.post('/api/me/push/status', json=sub).json()['enabled'])
            deliver_due(self.db, send, now=due - timedelta(seconds=1))
            self.assertEqual(calls, [])
            with ThreadPoolExecutor(4) as pool:
                list(pool.map(lambda _: deliver_due(self.db, send, now=due), range(4)))
            self.assertEqual(calls, [(sub, draft['id'])])
            self.assertFalse(self.client.post('/api/me/push/status', json=sub).json()['enabled'])
            self.assertEqual(self.client.get(self.path(draft)).json()['status'], 'pending')


class WebPushMessage(unittest.TestCase):
    def test_payload_only_contains_opaque_id_and_http_redirects_are_disabled(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        import http_ece
        from py_vapid import Vapid
        from requests import Response

        receiver = ec.generate_private_key(ec.SECP256R1())
        public = receiver.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        auth = b'a' * 16
        encode = lambda key: base64.urlsafe_b64encode(key).decode().rstrip('=')
        keys = Vapid()
        keys.generate_keys()
        secret = keys.private_key.private_numbers().private_value.to_bytes(32, 'big')
        config = ('public', encode(secret), 'mailto:push@example.test')
        sub = {'endpoint': 'https://fcm.googleapis.com/fcm/send/test', 'keys': {'p256dh': encode(public), 'auth': encode(auth)}}
        draft_id = 'a' * 64
        delivered = Response()
        delivered.status_code = 201
        with patch('requests.Session.send', return_value=delivered) as send:
            self.assertTrue(send_web_push(config, sub, draft_id))
        args, options = send.call_args
        message = args[0]
        self.assertFalse(options['allow_redirects'])
        self.assertEqual(message.headers['Content-Encoding'], 'aes128gcm')
        plain = http_ece.decrypt(message.body, private_key=receiver, auth_secret=auth, version='aes128gcm')
        self.assertEqual(json.loads(plain), {'draftId': draft_id})
