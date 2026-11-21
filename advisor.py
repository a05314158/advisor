import logging
import os
import secrets
import re
import base64
import hashlib
import json
from time import monotonic
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from catalog import CATEGORIES, SEED, bank_names, bank_public, connect, initialize, rows
PAGE = Path(__file__).with_name('wallet.html')



def recommend(category: str, amount: int, day: date, rules=None, own=None) -> dict:
    rules = SEED if rules is None else rules
    today = day.isoformat()
    matches = []
    for rule in rules:
        card = rule['cardId']
        if (rule['categoryId'] != category or amount < rule['minAmountKopecks']
                or not active(rule, today) or (own is not None and card not in own)):
            continue
        raw = (amount * rule['rateBps'] + 5000) // 10000
        cap = rule['limitKopecks']
        matches.append({**card_info(card), **rule, 'cashbackKopecks': raw if cap is None else min(raw, cap),
                        'limitApplied': cap is not None and raw > cap})
    matches.sort(key=lambda x: (-x['cashbackKopecks'], x['cardId']))
    def canonical(items):
        return sorted(items, key=lambda r: (r['cardId'], r['categoryId'], r['validFrom']))
    snapshot = canonical(rules)
    version = 'training-v1' if snapshot == canonical(SEED) else hashlib.sha256(
        json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    return dict(asOf=today, catalogVersion=version, top3=matches[:3], allMatches=matches)


def month_totals(items):
    calculated = sum(item['chosenKopecks'] for item in items)
    recommended = sum(item['recommendedKopecks'] for item in items)
    usual_values = [item['usualKopecks'] for item in items]
    usual = None if not items or any(value is None for value in usual_values) else sum(usual_values)
    return {
        'count': len(items),
        'calculatedKopecks': calculated,
        'recommendedKopecks': recommended,
        'missedKopecks': recommended - calculated,
        'usualKopecks': usual,
        'versusUsualKopecks': None if usual is None else calculated - usual,
    }


def active(rule, today):
    return rule['validFrom'] <= today and (rule['validUntilExclusive'] is None or today < rule['validUntilExclusive'])


def card_info(card):
    return dict(cardId=card, bankName=f'Учебный банк {card}', cardName=f'Карта {card}')


VISION_MODEL = 'gemini-2.5-flash-lite'
VISION_URL = 'https://api.aitunnel.ru/v1/chat/completions'
IMAGE_TYPES = {'image/jpeg': b'\xff\xd8\xff', 'image/png': b'\x89PNG', 'image/webp': b'RIFF'}


def vision_key():
    key = os.environ.get('ADVISOR_API_KEY', '').strip()
    env = Path(__file__).with_name('.env')
    if not key and env.exists():
        for line in env.read_text(encoding='utf-8').splitlines():
            if line.startswith('ADVISOR_API_KEY='):
                key = line.split('=', 1)[1].strip().strip('"').strip("'")
    return key


def decode_image(value):
    if not isinstance(value, str) or not value.startswith('data:image/'):
        raise ValueError('type')
    header, _, payload = value.partition(',')
    media = header[5:].split(';', 1)[0].lower().replace('image/jpg', 'image/jpeg')
    if media not in IMAGE_TYPES or 'base64' not in header or len(payload) > 6_000_000:
        raise ValueError('size' if len(payload) > 6_000_000 else 'type')
    try:
        blob = base64.b64decode(payload, validate=True)
    except (ValueError, TypeError):
        raise ValueError('type') from None
    if len(blob) > 4_000_000:
        raise ValueError('size')
    if len(blob) < 32 or not blob.startswith(IMAGE_TYPES[media]):
        raise ValueError('type')
    if media == 'image/webp' and blob[8:12] != b'WEBP':
        raise ValueError('type')
    return f'data:{media};base64,{base64.b64encode(blob).decode()}'


ALIASES = {
    'продукты': 'supermarkets', 'супермаркет': 'supermarkets', 'рестораны': 'cafe',
    'заправки': 'fuel', 'топливо': 'fuel', 'аптека': 'pharmacy',
    'маркетплейс': 'marketplace', 'жкх': 'utilities', 'связь': 'utilities',
    'прочие': 'all', 'остальные': 'all', 'на все покупки': 'all', 'все покупки': 'all',
    'кино и театр': 'entertainment', 'кино': 'entertainment', 'театр': 'entertainment',
    'такси': 'transport', 'фастфуд': 'cafe', 'быстрое питание': 'cafe',
}


def as_float(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    cleaned = value.replace(',', '.').replace('\u00a0', '').replace(' ', '')
    cleaned = ''.join(ch for ch in cleaned if ch.isdigit() or ch == '.')
    if not cleaned or cleaned == '.' or cleaned.count('.') > 1:
        return None
    return float(cleaned)


def category_id(value):
    if not isinstance(value, str):
        return None
    key = value.strip().casefold()
    if key in CATEGORIES:
        return key
    for cid, name in CATEGORIES.items():
        if name.casefold() == key:
            return cid
    return ALIASES.get(key)


def parse_rules(text):
    if not isinstance(text, str):
        raise ValueError('empty')
    raw = text.strip()
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[-1].rsplit('```', 1)[0]
    starts = [i for i in (raw.find('{'), raw.find('[')) if i >= 0]
    if not starts:
        raise ValueError('empty')
    end = max(raw.rfind('}'), raw.rfind(']'))
    data = json.loads(raw[min(starts):end + 1])
    items = data.get('rules') if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError('shape')
    cleaned = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        category = category_id(item.get('categoryId'))
        rate = as_float(item.get('ratePercent'))
        if category is None or rate is None:
            continue
        bps = int(round(rate * 100))
        if not 0 <= bps <= 10000:
            continue
        amount = as_float(item.get('limitRub'))
        kopecks = None
        if amount is not None:
            if amount < 0:
                continue
            kopecks = int(round(amount * 100))
            if kopecks > 10**12:
                continue
        previous = cleaned.get(category)
        if previous is None or bps > previous['rateBps']:
            cleaned[category] = dict(categoryId=category, rateBps=bps, limitKopecks=kopecks)
    if not cleaned:
        raise ValueError('no rules')
    return [cleaned[key] for key in CATEGORIES if key in cleaned]


def read_cashback(image):
    key = vision_key()
    if not key:
        raise RuntimeError('unavailable')
    names = '\n'.join(f'- {category_id}: {name}' for category_id, name in CATEGORIES.items())
    prompt = (
        'На скриншоте условия кэшбэка банковской карты. Верни только JSON '
        '{"rules":[{"categoryId":"...","ratePercent":5,"limitRub":null}]}. '
        'categoryId бери только из списка. ratePercent — проценты как на скрине, 5 означает 5%. '
        'limitRub — лимит в рублях или null, если лимита нет. '
        'Оставляй только категории, которые реально видны, и не выдумывай проценты. '
        '«На все покупки» — all, «Кино и театр» — entertainment, «Такси» и «Транспорт» — transport, '
        '«Фастфуд» — cafe.\n' + names
    )
    response = httpx.post(
        VISION_URL,
        headers={'Authorization': f'Bearer {key}'},
        json={'model': VISION_MODEL, 'temperature': 0, 'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': prompt},
            {'type': 'image_url', 'image_url': {'url': image}},
        ]}]},
        timeout=40,
    )
    response.raise_for_status()
    content = response.json()['choices'][0]['message']['content']
    if isinstance(content, list):
        content = ''.join(part.get('text', '') for part in content if isinstance(part, dict))
    return parse_rules(content)


COOKIE = 'advisor_session'
LOGIN_RE = re.compile(r'[A-Za-z0-9_]{3,32}')
PASSWORD_ROUNDS = 600_000
LOGINS = {}
LOGIN_LIMIT = 8
LOGIN_WINDOW = 600


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PASSWORD_ROUNDS)
    return f'{salt.hex()}:{digest.hex()}'


def password_matches(password, stored):
    try:
        salt_hex, digest_hex = stored.split(':', 1)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt_hex), PASSWORD_ROUNDS)
    except (ValueError, AttributeError):
        return False
    try:
        return secrets.compare_digest(digest.hex(), digest_hex)
    except ValueError:
        return False


def allow_login(login):
    now = monotonic()
    recent = [stamp for stamp in LOGINS.get(login, ()) if now - stamp < LOGIN_WINDOW]
    if len(recent) >= LOGIN_LIMIT:
        LOGINS[login] = recent
        return False
    recent.append(now)
    LOGINS[login] = recent
    return True


def session_response(payload, status, session, request):
    response = JSONResponse(payload, status)
    response.set_cookie(COOKIE, session, httponly=True, samesite='strict', max_age=31536000, path='/',
                        secure=request.url.scheme == 'https')
    return response
SHOTS = {}
SHOT_WINDOW = 3600
SHOT_LIMIT = 8
GLOBAL_SHOTS = []
GLOBAL_LIMIT = 30


def allow_screenshot(session):
    return True


def session_id(request):
    value = request.cookies.get(COOKIE, '')
    return value if re.fullmatch(r'[A-Za-z0-9_-]{43}', value) else None


def create_app(db_path):
    @asynccontextmanager
    async def lifespan(_):
        initialize(db_path)
        yield

    app = FastAPI(title='Советник', lifespan=lifespan)

    @app.middleware('http')
    async def no_api_cache(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/')
    def home():
        return FileResponse(PAGE)

    @app.get('/welcome.html', include_in_schema=False)
    def welcome():
        return FileResponse(PAGE.with_name('welcome.html'))

    @app.get('/pocket.webp', include_in_schema=False)
    def pocket():
        return FileResponse(PAGE.with_name('pocket.webp'), media_type='image/webp')

    @app.get('/api/auth/me')
    def auth_me(request: Request):
        session = session_id(request)
        if not session:
            return JSONResponse({'authenticated': False})
        with connect(db_path) as db:
            user = db.execute('SELECT login FROM users WHERE session = ?', (session,)).fetchone()
        return {'authenticated': bool(user), 'login': user[0] if user else None}

    @app.post('/api/auth/register', status_code=201)
    def register(body: dict, request: Request):
        login, password = body.get('login'), body.get('password')
        if not isinstance(login, str) or not LOGIN_RE.fullmatch(login):
            return JSONResponse({'message': 'Логин: 3–32 латинские буквы, цифры или _'}, 422)
        if not isinstance(password, str) or not 4 <= len(password) <= 72:
            return JSONResponse({'message': 'Пароль — минимум 4 знака'}, 422)
        session = secrets.token_urlsafe(32)
        login = login.lower()
        with connect(db_path) as db:
            if db.execute('SELECT 1 FROM users WHERE login = ?', (login,)).fetchone():
                return JSONResponse({'message': 'Такой логин уже есть'}, 409)
            db.execute('INSERT INTO users VALUES (?, ?, ?, ?)',
                       (session, login, hash_password(password), datetime.now(UTC).date().isoformat()))
        return session_response({'login': login}, 201, session, request)

    @app.post('/api/auth/login')
    def login(body: dict, request: Request):
        login, password = body.get('login'), body.get('password')
        if not isinstance(login, str) or not isinstance(password, str):
            return JSONResponse({'message': 'Неверный логин или пароль'}, 401)
        key = login.strip().lower()
        if not allow_login(key):
            return JSONResponse({'message': 'Слишком много попыток. Попробуйте позже'}, 429)
        with connect(db_path) as db:
            user = db.execute('SELECT session, password_hash FROM users WHERE login = ?', (key,)).fetchone()
        if not user or not password_matches(password, user[1]):
            return JSONResponse({'message': 'Неверный логин или пароль'}, 401)
        return session_response({'login': key}, 200, user[0], request)

    @app.post('/api/auth/logout', status_code=204)
    def logout():
        response = Response(status_code=204)
        response.delete_cookie(COOKIE, path='/')
        return response

    @app.get('/healthz')
    def health():
        with connect(db_path) as db:
            db.execute('SELECT 1 FROM rules LIMIT 1').fetchone()
        return {'status': 'ok'}

    @app.get('/api/cards')
    def cards(categoryId: str | None = None):
        if categoryId is not None and categoryId not in CATEGORIES:
            return JSONResponse({'field': 'categoryId', 'code': 'unknown_category'}, 422)
        today = datetime.now(UTC).date().isoformat()
        with connect(db_path) as db:
            result = {}
            for rule in rows(db):
                card = rule['cardId']
                if categoryId is None or (rule['categoryId'] == categoryId and active(rule, today)):
                    result.setdefault(card, dict(**card_info(card), rules=[]))
                    if active(rule, today):
                        result[card]['rules'].append(rule)
        return list(result.values())

    @app.get('/api/cards/{card}')
    def details(card: str):
        today = datetime.now(UTC).date().isoformat()
        with connect(db_path) as db:
            rules = [r for r in rows(db) if r['cardId'] == card]
        if not rules:
            return JSONResponse({'code': 'unknown_card'}, 404)
        return dict(**card_info(card), rules=[r for r in rules if active(r, today)])

    def saved(db, request):
        return [row[0] for row in db.execute('SELECT cardId FROM saved WHERE session = ? ORDER BY cardId',
                                              (session_id(request),))]

    @app.get('/api/me/cards')
    def my_cards(request: Request):
        with connect(db_path) as db:
            return saved(db, request)

    def manual_cards(db, request):
        return [dict(cardId=card, name=name, updatedOn=updated, rules=json.loads(rules))
                for card, name, updated, rules in db.execute(
                    'SELECT card_id, name, updated_on, rules_json FROM manual_cards WHERE session = ? ORDER BY rowid',
                    (session_id(request),))]

    @app.get('/api/me/manual-cards')
    def list_manual_cards(request: Request):
        with connect(db_path) as db:
            return manual_cards(db, request)

    @app.post('/api/me/manual-cards', status_code=201)
    def create_manual_card(body: dict, request: Request):
        name, rules = body.get('name'), body.get('rules')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            return JSONResponse({'code': 'invalid_name'}, 422)
        if not isinstance(rules, list) or not 0 <= len(rules) <= len(CATEGORIES):
            return JSONResponse({'code': 'invalid_rules'}, 422)
        cleaned, seen = [], set()
        for rule in rules:
            if not isinstance(rule, dict):
                return JSONResponse({'code': 'invalid_rules'}, 422)
            category, rate, limit = rule.get('categoryId'), rule.get('rateBps'), rule.get('limitKopecks')
            if (not isinstance(category, str) or category not in CATEGORIES or category in seen
                    or type(rate) is not int or not 0 <= rate <= 10000
                    or (limit is not None and (type(limit) is not int or not 0 <= limit <= 10**12))):
                return JSONResponse({'code': 'invalid_rules'}, 422)
            seen.add(category)
            cleaned.append(dict(categoryId=category, rateBps=rate, limitKopecks=limit))
        session = session_id(request) or secrets.token_urlsafe(32)
        card = 'manual-' + secrets.token_hex(12)
        today = datetime.now(UTC).date().isoformat()
        with connect(db_path) as db:
            db.execute('INSERT INTO manual_cards VALUES (?, ?, ?, ?, ?)',
                       (session, card, name.strip(), today, json.dumps(cleaned)))
        response = JSONResponse({'cardId': card}, 201)
        response.set_cookie(COOKIE, session, httponly=True, samesite='strict', max_age=31536000, path='/',
                            secure=request.url.scheme == 'https')
        return response

    @app.get('/api/meta')
    def meta():
        return {'banks': bank_public(), 'categories': CATEGORIES}

    @app.post('/api/me/cashback-screenshot', status_code=201)
    def cashback_screenshot(body: dict, request: Request):
        bank_id, image = body.get('bankId'), body.get('image')
        banks = bank_names()
        if bank_id not in banks:
            return JSONResponse({'message': 'Выберите банк из списка'}, 422)
        try:
            image = decode_image(image)
        except ValueError as error:
            message = 'Скриншот больше 4 МБ' if error.args == ('size',) else 'Прикрепите скриншот в JPG, PNG или WebP'
            return JSONResponse({'message': message}, 422)
        session = session_id(request)
        with connect(db_path) as db:
            user = db.execute('SELECT 1 FROM users WHERE session = ?', (session,)).fetchone() if session else None
        if not user:
            return JSONResponse({'message': 'Войдите, чтобы добавить карту'}, 401)
        if not allow_screenshot(session):
            return JSONResponse({'message': 'Слишком много скриншотов. Попробуйте позже'}, 429)
        try:
            rules = read_cashback(image)
        except ValueError:
            return JSONResponse({'message': 'На скриншоте не видно категорий кэшбэка'}, 422)
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            logging.getLogger('advisor').warning('cashback http %s', status)
            if status in (401, 403):
                return JSONResponse({'message': 'Сервис распознавания не принял ключ'}, 502)
            return JSONResponse({'message': 'Не удалось разобрать категории. Попробуйте ещё раз'}, 502)
        except (httpx.HTTPError, KeyError, TypeError, RuntimeError) as error:
            logging.getLogger('advisor').warning('cashback %s', type(error).__name__)
            return JSONResponse({'message': 'Не удалось разобрать категории. Попробуйте ещё раз'}, 502)
        target = body.get('cardId')
        today = datetime.now(UTC).date().isoformat()
        payload = json.dumps(rules, ensure_ascii=False)
        with connect(db_path) as db:
            if isinstance(target, str) and db.execute(
                    'SELECT 1 FROM manual_cards WHERE session = ? AND card_id = ?', (session, target)).fetchone():
                db.execute('UPDATE manual_cards SET rules_json = ?, updated_on = ? WHERE session = ? AND card_id = ?',
                           (payload, today, session, target))
                name = db.execute('SELECT name FROM manual_cards WHERE session = ? AND card_id = ?',
                                  (session, target)).fetchone()[0]
                return {'cardId': target, 'name': name, 'rules': rules}
            card = 'manual-' + secrets.token_hex(12)
            db.execute('INSERT INTO manual_cards VALUES (?, ?, ?, ?, ?)',
                       (session, card, banks[bank_id], today, payload))
        return {'cardId': card, 'name': banks[bank_id], 'rules': rules}

    @app.delete('/api/me/manual-cards/{card}', status_code=204)
    def delete_manual_card(card: str, request: Request):
        with connect(db_path) as db:
            db.execute('DELETE FROM manual_cards WHERE session = ? AND card_id = ?', (session_id(request), card))
        return Response(status_code=204)

    @app.put('/api/me/cards/{card}', status_code=204)
    def add_card(card: str, request: Request):
        session = session_id(request) or secrets.token_urlsafe(32)
        with connect(db_path) as db:
            if not db.execute('SELECT 1 FROM rules WHERE cardId = ? LIMIT 1', (card,)).fetchone():
                return JSONResponse({'code': 'unknown_card'}, 404)
            db.execute('INSERT OR IGNORE INTO saved VALUES (?, ?)', (session, card))
        response = Response(status_code=204)
        response.set_cookie(COOKIE, session, httponly=True, samesite='strict', max_age=31536000, path='/',
                            secure=request.url.scheme == 'https')
        return response

    @app.delete('/api/me/cards/{card}', status_code=204)
    def remove_card(card: str, request: Request):
        with connect(db_path) as db:
            db.execute('DELETE FROM saved WHERE session = ? AND cardId = ?', (session_id(request), card))
        return Response(status_code=204)

    @app.post('/api/recommendations')
    def recommendations(body: dict, request: Request):
        category, amount, scope = body.get('categoryId'), body.get('amountKopecks'), body.get('scope')
        if type(amount) is not int or not 0 < amount <= 10**12:
            return JSONResponse({'field': 'amountKopecks', 'code': 'positive_integer_required'}, 422)
        if not isinstance(category, str) or category not in CATEGORIES:
            return JSONResponse({'field': 'categoryId', 'code': 'unknown_category'}, 422)
        if scope not in ('all', 'mine'):
            return JSONResponse({'field': 'scope', 'code': 'unknown_scope'}, 422)
        with connect(db_path) as db:
            db.execute('BEGIN')
            rules, own = owned_rules(db, request)
            if scope != 'mine':
                rules, own = rows(db), None
        return recommend(category, amount, datetime.now(UTC).date(), rules, own)

    def owned_rules(db, request):
        rules = rows(db)
        own = set(saved(db, request))
        for card in manual_cards(db, request):
            own.add(card['cardId'])
            rules.extend({**rule, 'cardId': card['cardId'], 'cardName': card['name'],
                          'bankName': 'Со скриншота', 'minAmountKopecks': 1,
                          'validFrom': card['updatedOn'], 'updatedOn': card['updatedOn'],
                          'validUntilExclusive': None} for rule in card['rules'])
        return rules, own

    def require_user(request):
        session = session_id(request)
        if not session:
            return None
        with connect(db_path) as db:
            user = db.execute('SELECT 1 FROM users WHERE session = ?', (session,)).fetchone()
        return session if user else None

    @app.post('/api/me/purchases', status_code=201)
    def record_purchase(body: dict, request: Request):
        session = require_user(request)
        if not session:
            return JSONResponse({'message': 'Войдите, чтобы записать покупку'}, 401)
        category, amount, chosen = body.get('categoryId'), body.get('amountKopecks'), body.get('chosenCardId')
        if type(amount) is not int or not 0 < amount <= 10**12:
            return JSONResponse({'message': 'Введите сумму'}, 422)
        if not isinstance(category, str) or category not in CATEGORIES:
            return JSONResponse({'message': 'Выберите категорию'}, 422)
        if not isinstance(chosen, str):
            return JSONResponse({'message': 'Выберите карту'}, 422)
        today = datetime.now(UTC).date()
        with connect(db_path) as db:
            rules, own = owned_rules(db, request)
            result = recommend(category, amount, today, rules, own)
            picked = next((item for item in result['allMatches'] if item['cardId'] == chosen), None)
            if not picked:
                return JSONResponse({'message': 'Эта карта не даёт кэшбэк в выбранной категории'}, 422)
            best = result['top3'][0]
            usual = db.execute('SELECT card_id FROM usual_card WHERE session = ?', (session,)).fetchone()
            usual_hit = next((item for item in result['allMatches'] if usual and item['cardId'] == usual[0]), None)
            db.execute('''INSERT INTO purchases
                (session, bought_on, category_id, amount_kopecks,
                 recommended_card, recommended_name, recommended_kopecks,
                 chosen_card, chosen_name, chosen_kopecks, usual_kopecks, catalog_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (session, today.isoformat(), category, amount,
                 best['cardId'], best['cardName'], best['cashbackKopecks'],
                 picked['cardId'], picked['cardName'], picked['cashbackKopecks'],
                 None if usual_hit is None else usual_hit['cashbackKopecks'],
                 result['catalogVersion']))
        return {'calculatedKopecks': picked['cashbackKopecks'], 'recommendedKopecks': best['cashbackKopecks']}

    @app.get('/api/me/stats')
    def stats(request: Request):
        session = require_user(request)
        if not session:
            return JSONResponse({'message': 'Войдите'}, 401)
        month = datetime.now(UTC).date().strftime('%Y-%m')
        with connect(db_path) as db:
            usual = db.execute('SELECT card_id FROM usual_card WHERE session = ?', (session,)).fetchone()
            raw = db.execute('''SELECT bought_on, category_id, amount_kopecks, recommended_name, recommended_kopecks,
                chosen_name, chosen_kopecks, usual_kopecks FROM purchases
                WHERE session = ? AND bought_on LIKE ? ORDER BY id DESC''', (session, month + '%')).fetchall()
        items = [dict(date=row[0], categoryId=row[1], amountKopecks=row[2], recommendedName=row[3],
                      recommendedKopecks=row[4], chosenName=row[5], chosenKopecks=row[6], usualKopecks=row[7])
                 for row in raw]
        return {'month': month, 'usualCardId': usual[0] if usual else None, 'purchases': items, **month_totals(items),
                'note': 'Это расчёт по записанным покупкам, не начисление банка. Остаток месячного лимита по операциям не считаем.'}

    @app.put('/api/me/usual-card', status_code=204)
    def set_usual(body: dict, request: Request):
        session = require_user(request)
        if not session:
            return JSONResponse({'message': 'Войдите'}, 401)
        card = body.get('cardId')
        if not isinstance(card, str) or not card:
            return JSONResponse({'message': 'Выберите карту'}, 422)
        with connect(db_path) as db:
            db.execute('INSERT INTO usual_card VALUES (?, ?) ON CONFLICT(session) DO UPDATE SET card_id = excluded.card_id',
                       (session, card))
        return Response(status_code=204)

    @app.post('/api/me/stats/comment')
    def stats_comment(request: Request):
        session = require_user(request)
        if not session:
            return JSONResponse({'message': 'Войдите'}, 401)
        report = stats(request)
        if isinstance(report, JSONResponse):
            return report
        key = vision_key()
        if not key:
            return JSONResponse({'message': 'Сервис разбора недоступен'}, 502)
        prompt = (
            'Коротко по-русски, 3 предложения. Это расчётный кэшбэк, не выплата банка. '
            f"Месяц {report['month']}: покупок {report['count']}, "
            f"по выбранным картам {report['calculatedKopecks']} копеек, "
            f"по лучшей рекомендации {report['recommendedKopecks']} копеек, "
            f"разница {report['missedKopecks']} копеек. "
            f"К обычной карте: {report['versusUsualKopecks']} копеек. "
            'Не выдумывай покупки.'
        )
        try:
            response = httpx.post(VISION_URL, headers={'Authorization': f'Bearer {key}'},
                                  json={'model': VISION_MODEL, 'temperature': 0,
                                        'messages': [{'role': 'user', 'content': prompt}]}, timeout=40)
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']
        except (httpx.HTTPError, KeyError, TypeError):
            return JSONResponse({'message': 'Не удалось разобрать статистику'}, 502)
        return {'comment': content if isinstance(content, str) else ''}

    return app


app = create_app(Path(os.environ.get('ADVISOR_DB', 'advisor.sqlite3')))
