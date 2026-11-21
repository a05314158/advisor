"""Deferred purchase confirmation and opt-in Web Push delivery."""
import asyncio
import base64
import binascii
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, Request, Response

from catalog import connect

LOG = logging.getLogger(__name__)
DRAFT_COLUMNS = 'id, state, category, amount, card_id, paid_on, remind_at, purchase_id, snapshot, timezone'


def setup_reminders(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS wallet_purchase_drafts (
            id TEXT PRIMARY KEY, session TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
            category TEXT NOT NULL, amount INTEGER NOT NULL, card_id TEXT NOT NULL,
            paid_on TEXT NOT NULL, remind_at TEXT NOT NULL, snapshot TEXT NOT NULL,
            timezone TEXT NOT NULL, purchase_id INTEGER, claimed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS wallet_drafts_owner ON wallet_purchase_drafts(session, state);
        CREATE INDEX IF NOT EXISTS wallet_drafts_due ON wallet_purchase_drafts(remind_at)
            WHERE state = 'pending' AND claimed_at IS NULL;
        CREATE TABLE IF NOT EXISTS wallet_push_subscriptions (
            endpoint TEXT PRIMARY KEY, session TEXT NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS wallet_push_owner ON wallet_push_subscriptions(session, updated_at);
    """)


def now_utc():
    return datetime.now(UTC)


def settings():
    public = os.getenv('ADVISOR_VAPID_PUBLIC_KEY')
    private = os.getenv('ADVISOR_VAPID_PRIVATE_KEY')
    subject = os.getenv('ADVISOR_VAPID_SUBJECT')
    return (public, private, subject) if public and private and subject else None


def valid_endpoint(endpoint):
    if not isinstance(endpoint, str) or len(endpoint) > 2048 or not endpoint.isascii():
        return False
    try:
        url = urlsplit(endpoint)
        host = url.hostname or ''
        trusted = host in {'fcm.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com'}
        edge = re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)*\.notify\.windows\.com', host)
        return bool((trusted or edge) and url.scheme == 'https' and url.netloc == host
                    and url.path.startswith('/') and not url.fragment
                    and all(32 < ord(char) < 127 for char in endpoint)
                    and '\\' not in endpoint)
    except ValueError:
        return False


def push_subscription(body):
    endpoint, keys = body.get('endpoint'), body.get('keys')
    if not valid_endpoint(endpoint) or not isinstance(keys, dict):
        raise HTTPException(422, 'Подписка на уведомления не поддерживается')
    try:
        clean = {}
        for field, size in [('p256dh', 65), ('auth', 16)]:
            value = keys.get(field)
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+={0,2}', value) or len(value) > 90:
                raise ValueError
            decoded = base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
            if len(decoded) != size or (field == 'p256dh' and decoded[0] != 4):
                raise ValueError
            clean[field] = value
    except (ValueError, binascii.Error):
        raise HTTPException(422, 'Подписка на уведомления не поддерживается') from None
    return {'endpoint': endpoint, 'keys': clean}


def send_web_push(config, subscription, draft_id):
    from pywebpush import WebPushException, webpush
    from requests import Session

    class DirectSession(Session):
        def request(self, *args, **kwargs):
            kwargs['allow_redirects'] = False
            return super().request(*args, **kwargs)

    _, private, subject = config
    with DirectSession() as session:
        try:
            webpush(subscription, data=json.dumps({'draftId': draft_id}), ttl=6 * 3600,
                    vapid_private_key=private, vapid_claims={'sub': subject}, timeout=8,
                    requests_session=session)
        except WebPushException as error:
            if error.response is not None and error.response.status_code in (404, 410):
                return False
            raise
    return True


def deliver_due(db_path, send, *, now=None):
    now = now if now is not None else now_utc()
    with connect(db_path) as db:
        candidates = db.execute("""
            SELECT d.id, d.session, s.endpoint, s.payload FROM wallet_purchase_drafts d
            JOIN wallet_push_subscriptions s ON s.endpoint = (
                SELECT endpoint FROM wallet_push_subscriptions WHERE session = d.session
                ORDER BY updated_at DESC, endpoint LIMIT 1
            )
            WHERE d.state = 'pending' AND d.claimed_at IS NULL AND d.remind_at BETWEEN ? AND ?
            ORDER BY d.remind_at, d.id LIMIT 25
        """, ((now - timedelta(hours=6)).isoformat(), now.isoformat())).fetchall()
    for draft_id, session, endpoint, payload in candidates:
        with connect(db_path) as db:
            claimed = db.execute("""
                UPDATE wallet_purchase_drafts SET claimed_at = ?
                WHERE id = ? AND state = 'pending' AND claimed_at IS NULL
                  AND EXISTS (SELECT 1 FROM wallet_push_subscriptions
                              WHERE session = ? AND endpoint = ? AND payload = ?)
            """, (now.isoformat(), draft_id, session, endpoint, payload)).rowcount
        if not claimed:
            continue
        try:
            if not send(json.loads(payload), draft_id):
                with connect(db_path) as db:
                    db.execute('DELETE FROM wallet_push_subscriptions WHERE session = ? AND endpoint = ? AND payload = ?',
                               (session, endpoint, payload))
        except Exception as error:
            # Delivery errors may embed endpoints or keys.
            LOG.warning('Web Push delivery failed (%s)', type(error).__name__)


@asynccontextmanager
async def reminder_worker(db_path):
    config = settings()

    async def run():
        while True:
            try:
                await asyncio.to_thread(deliver_due, db_path, lambda sub, draft_id: send_web_push(config, sub, draft_id))
            except Exception:
                LOG.exception('Could not scan due purchase reminders')
            await asyncio.sleep(30)

    worker = asyncio.create_task(run()) if config else None
    try:
        yield
    finally:
        if worker:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)


def view(row):
    draft_id, state, category, amount, card, day, remind, purchase_id, snapshot, _ = row
    snapshot = json.loads(snapshot)
    return dict(id=draft_id, status=state, categoryId=category, amountKopecks=amount,
                chosenCardId=card, paidOn=day, remindAt=remind, purchaseId=purchase_id,
                cards=[dict(id=key, name=name) for key, name in snapshot['cards'].items()])


def mount_reminders(app, db_path, require_user, make_snapshot, rank, write_purchase):
    def owner(request):
        session = require_user(request)
        if session is None:
            raise HTTPException(401, 'Войдите в кошелёк')
        return session

    def find(db, session, draft_id):
        row = db.execute(f'SELECT {DRAFT_COLUMNS} FROM wallet_purchase_drafts WHERE session = ? AND id = ?',
                         (session, draft_id)).fetchone()
        if not row:
            raise HTTPException(404, 'Черновик не найден')
        return row

    @app.post('/api/me/purchase-drafts', status_code=201)
    def create(body: dict, request: Request):
        session = owner(request)
        retry_key = body.get('requestId')
        category, amount, card = body.get('categoryId'), body.get('amountKopecks'), body.get('chosenCardId')
        if (not isinstance(retry_key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{22,64}', retry_key)
                or not isinstance(category, str) or not isinstance(card, str)
                or type(amount) is not int or not 0 < amount <= 10**12):
            raise HTTPException(422, 'Выберите категорию, сумму и карту')
        draft_id = sha256(f'{session}:{retry_key}'.encode()).hexdigest()
        timezone = body.get('timezone', 'UTC')
        try:
            if not isinstance(timezone, str) or len(timezone) > 64:
                raise ValueError
            zone = ZoneInfo(timezone)
        except (ValueError, ZoneInfoNotFoundError):
            raise HTTPException(422, 'Не удалось определить часовой пояс') from None
        now = now_utc()
        day = now.astimezone(zone).date()
        due = datetime.combine(day + timedelta(days=1), time(12), zone).astimezone(UTC)
        with connect(db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute(f'SELECT {DRAFT_COLUMNS} FROM wallet_purchase_drafts WHERE session = ? AND id = ?',
                             (session, draft_id)).fetchone()
            if old:
                original = json.loads(old[8])['original']
                if original != [category, amount, card, timezone]:
                    raise HTTPException(409, 'Черновик уже существует с другими данными')
                return view(old)
            snapshot = make_snapshot(db, request, category, now.date())
            if card not in snapshot['cards'] or not any(
                    item['cardId'] == card for item in rank(category, amount, day, snapshot, day)['allMatches']):
                raise HTTPException(422, 'Для выбранной карты нет расчёта по этой покупке')
            snapshot['original'] = [category, amount, card, timezone]
            db.execute("""INSERT INTO wallet_purchase_drafts
                (id, session, category, amount, card_id, paid_on, remind_at, snapshot, timezone)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                       (draft_id, session, category, amount, card, day.isoformat(), due.isoformat(),
                        json.dumps(snapshot), timezone))
            return view(find(db, session, draft_id))

    @app.get('/api/me/purchase-drafts')
    def pending(request: Request):
        session = owner(request)
        with connect(db_path) as db:
            return {'drafts': [view(row) for row in db.execute(
                f"""SELECT {DRAFT_COLUMNS} FROM wallet_purchase_drafts
                    WHERE session = ? AND state = 'pending' ORDER BY remind_at, id""", (session,))]}

    @app.get('/api/me/purchase-drafts/{draft_id}')
    def detail(draft_id: str, request: Request):
        session = owner(request)
        with connect(db_path) as db:
            return view(find(db, session, draft_id))

    @app.put('/api/me/purchase-drafts/{draft_id}/decision')
    def decide(draft_id: str, body: dict, request: Request):
        session = owner(request)
        action = body.get('action')
        if action not in ('confirm', 'decline'):
            raise HTTPException(422, 'Выберите действие')
        state = 'confirmed' if action == 'confirm' else 'declined'
        with connect(db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = find(db, session, draft_id)
            if row[1] != 'pending':
                if row[1] != state:
                    raise HTTPException(409, 'Черновик уже закрыт')
                return view(row)
            if action == 'decline':
                db.execute("UPDATE wallet_purchase_drafts SET state = 'declined' WHERE id = ?", (draft_id,))
                return view(find(db, session, draft_id))
            _, _, category, original_amount, original_card, original_day, _, _, raw, timezone = row
            snapshot = json.loads(raw)
            amount = body.get('amountKopecks', original_amount)
            card = body.get('chosenCardId', original_card)
            raw_day = body.get('paidOn', original_day)
            try:
                day = date.fromisoformat(raw_day)
                if raw_day != day.isoformat() or day > now_utc().astimezone(ZoneInfo(timezone)).date():
                    raise ValueError
            except (TypeError, ValueError):
                raise HTTPException(422, 'Проверьте дату оплаты') from None
            if type(amount) is not int or not 0 < amount <= 10**12:
                raise HTTPException(422, 'Проверьте сумму покупки')
            if not isinstance(card, str) or card not in snapshot['cards']:
                raise HTTPException(422, 'Выберите карту из списка')
            result = rank(category, amount, day, snapshot, date.fromisoformat(original_day))
            picked = next((item for item in result['allMatches'] if item['cardId'] == card), None)
            if picked is None:
                result = dict(top3=[], allMatches=[], catalogVersion='draft-estimate-unavailable')
                picked = dict(cardId=card, cardName=snapshot['cards'][card], cashbackKopecks=0)
            entry = write_purchase(db, session, day, category, amount, result, picked, snapshot['usual'])
            db.execute("""UPDATE wallet_purchase_drafts SET state = 'confirmed', amount = ?, card_id = ?,
                        paid_on = ?, purchase_id = ? WHERE id = ?""",
                       (amount, card, day.isoformat(), entry['id'], draft_id))
            return view(find(db, session, draft_id))

    @app.get('/api/me/push')
    def push_config(request: Request):
        owner(request)
        config = settings()
        return {'publicKey': config[0] if config else None}

    @app.post('/api/me/push/status')
    def push_status(body: dict, request: Request):
        session = owner(request)
        with connect(db_path) as db:
            row = db.execute('SELECT 1 FROM wallet_push_subscriptions WHERE session = ? AND endpoint = ?',
                             (session, str(body.get('endpoint', '')))).fetchone()
        return {'enabled': row is not None}

    @app.put('/api/me/push', status_code=204)
    def enable_push(body: dict, request: Request):
        session = owner(request)
        if not settings():
            raise HTTPException(503, 'Уведомления пока недоступны')
        sub = push_subscription(body)
        with connect(db_path) as db:
            db.execute("""INSERT INTO wallet_push_subscriptions VALUES (?, ?, ?, ?)
                ON CONFLICT(endpoint) DO UPDATE SET session = excluded.session,
                payload = excluded.payload, updated_at = excluded.updated_at""",
                       (sub['endpoint'], session, json.dumps(sub), now_utc().isoformat()))
        return Response(status_code=204)

    @app.delete('/api/me/push', status_code=204)
    def disable_push(body: dict, request: Request):
        session = owner(request)
        endpoint = body.get('endpoint')
        if not valid_endpoint(endpoint):
            raise HTTPException(422, 'Укажите подписку')
        with connect(db_path) as db:
            db.execute('DELETE FROM wallet_push_subscriptions WHERE session = ? AND endpoint = ?', (session, endpoint))
        return Response(status_code=204)
