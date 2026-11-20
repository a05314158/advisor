import os
import secrets
import re
import hashlib
import json
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from catalog import CATEGORIES, CATEGORY_GROUPS, SEED, connect, initialize, rows
from nearby import MAX_ACCURACY_METRES, search_places, within
PAGE = Path(__file__).with_name('index.html')
CATEGORY_IDS = {label.casefold(): category_id for category_id, label in CATEGORIES.items()}
CATEGORY_IDS['кафе и рестораны'] = 'cafe'



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


def active(rule, today):
    return rule['validFrom'] <= today and (rule['validUntilExclusive'] is None or today < rule['validUntilExclusive'])


def card_info(card):
    return dict(cardId=card, bankName=f'Учебный банк {card}', cardName=f'Карта {card}')


COOKIE = 'advisor_session'


def category_label(raw):
    return ' '.join(raw.split()) if isinstance(raw, str) else ''


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

    @app.get('/healthz')
    def health():
        with connect(db_path) as db:
            db.execute('SELECT 1 FROM rules LIMIT 1').fetchone()
        return {'status': 'ok'}

    @app.get('/api/categories')
    def categories():
        return CATEGORIES

    @app.get('/api/category-groups')
    def category_groups():
        return CATEGORY_GROUPS

    @app.get('/api/nearby')
    def nearby_config():
        return {'available': bool(os.environ.get('ADVISOR_2GIS_KEY'))}

    @app.post('/api/nearby')
    def nearby(body: dict):
        lat, lon, accuracy = body.get('latitude'), body.get('longitude'), body.get('accuracy')
        if not (within(lat, -90, 90) and within(lon, -180, 180) and within(accuracy, 0, 1000000)):
            return JSONResponse({'code': 'invalid_location'}, 422)
        if accuracy > MAX_ACCURACY_METRES:
            return {'status': 'low_accuracy', 'places': []}
        key = os.environ.get('ADVISOR_2GIS_KEY')
        if not key:
            return {'status': 'not_configured', 'places': []}
        try:
            places = search_places(key, lat, lon, accuracy)
        except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
            return {'status': 'unavailable', 'places': []}
        return {'status': 'ok', 'places': places}

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
        def display_rule(rule):
            label = rule.get('categoryName') or CATEGORIES[rule['categoryId']]
            return {**rule, 'categoryName': label, 'categoryKey': label.casefold()}

        return [dict(cardId=card, name=name, updatedOn=updated, rules=[display_rule(rule) for rule in json.loads(rules)])
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
        if not isinstance(rules, list) or not rules:
            return JSONResponse({'code': 'invalid_rules'}, 422)
        cleaned, seen = [], set()
        for rule in rules:
            if not isinstance(rule, dict):
                return JSONResponse({'code': 'invalid_rules'}, 422)
            category, rate, limit = rule.get('categoryId'), rule.get('rateBps'), rule.get('limitKopecks')
            label = category_label(rule['categoryName']) if 'categoryName' in rule else (
                CATEGORIES.get(category, '') if isinstance(category, str) else '')
            key = label.casefold()
            if (not 1 <= len(label) <= 80 or key in seen
                    or type(rate) is not int or not 0 <= rate <= 10000
                    or (limit is not None and (type(limit) is not int or not 0 <= limit <= 10**12))):
                return JSONResponse({'code': 'invalid_rules'}, 422)
            seen.add(key)
            cleaned.append(dict(categoryId=category if 'categoryName' not in rule else key,
                                categoryName=label, rateBps=rate, limitKopecks=limit))
        session = session_id(request) or secrets.token_urlsafe(32)
        card = 'manual-' + secrets.token_hex(12)
        today = datetime.now(UTC).date().isoformat()
        with connect(db_path) as db:
            db.execute('INSERT INTO manual_cards VALUES (?, ?, ?, ?, ?)',
                       (session, card, name.strip(), today, json.dumps(cleaned)))
        response = JSONResponse({'cardId': card}, 201)
        response.set_cookie(COOKIE, session, httponly=True, samesite='strict', max_age=31536000,
                            secure=request.url.scheme == 'https')
        return response

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
        response.set_cookie(COOKIE, session, httponly=True, samesite='strict', max_age=31536000,
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
        if scope == 'manual':
            label = category_label(category)
            category = label.casefold() if 1 <= len(label) <= 80 else ''
        if not isinstance(category, str) or not category or (scope != 'manual' and category not in CATEGORIES):
            return JSONResponse({'field': 'categoryId', 'code': 'unknown_category'}, 422)
        if scope not in ('all', 'mine', 'manual'):
            return JSONResponse({'field': 'scope', 'code': 'unknown_scope'}, 422)
        with connect(db_path) as db:
            db.execute('BEGIN')
            catalog_rules = [] if scope == 'manual' else rows(db)
            rules = list(catalog_rules)
            own = set() if scope == 'manual' else set(saved(db, request)) if scope == 'mine' else None
            if own is not None:
                for card in manual_cards(db, request):
                    own.add(card['cardId'])
                    for rule in card['rules']:
                        key = rule['categoryKey']
                        category_id = key if scope == 'manual' else CATEGORY_IDS.get(key, f'manual:{key}')
                        rules.append({**rule, 'categoryId': category_id,
                                      'cardId': card['cardId'], 'cardName': card['name'],
                                      'bankName': 'Введено вручную', 'minAmountKopecks': 1,
                                      'validFrom': card['updatedOn'], 'updatedOn': card['updatedOn'],
                                      'validUntilExclusive': None})
        day = datetime.now(UTC).date()
        result = recommend(category, amount, day, rules, own)
        if scope == 'mine' and not any(card['cashbackKopecks'] > 0 for card in result['top3']):
            unowned = {rule['cardId'] for rule in catalog_rules} - own
            alternatives = recommend(category, amount, day, catalog_rules, unowned)['top3']
            if alternatives and alternatives[0]['cashbackKopecks'] > 0:
                result['catalogSuggestion'] = alternatives[0]
        return result

    return app


app = create_app(Path(os.environ.get('ADVISOR_DB', 'advisor.sqlite3')))
