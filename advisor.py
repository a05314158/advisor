import os
import secrets
import re
import hashlib
import json
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from unicodedata import category as unicode_category, normalize

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from catalog import CATEGORIES, CATEGORY_GROUPS, SEED, connect, initialize, rows
from nearby import MAX_ACCURACY_METRES, search_places, within
from accounts import account, mount_accounts
from observability import mount_observability
from spending import mount_spending
PAGE = Path(__file__).with_name('index.html')
BUILD_REVISION = '$Format:%H$'
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
        cashback = raw if cap is None else min(raw, cap)
        remaining = rule.get('monthlyRemainingKopecks')
        monthly = rule.get('monthlyLimitKopecks') if remaining is None else remaining
        if monthly == 0:
            continue
        match = {**card_info(card), **rule, 'cashbackKopecks': cashback,
                 'limitApplied': cap is not None and raw > cap}
        if monthly is not None:
            match.update(cashbackKopecks=min(cashback, monthly), monthlyLimitApplied=cashback > monthly)
        matches.append(match)
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
    if not isinstance(raw, str) or any(unicode_category(char) in {'Cc', 'Cf', 'Cs'} for char in raw):
        return ''
    return ' '.join(normalize('NFC', raw).split())


def iso_day(raw):
    if not isinstance(raw, str):
        return False
    try:
        return date.fromisoformat(raw).isoformat() == raw
    except ValueError:
        return False


def session_id(request):
    value = request.cookies.get(COOKIE, '')
    return value if re.fullmatch(r'[A-Za-z0-9_-]{43}', value) else None


def card_owner(db, request):
    user = account(db, request)
    return 'account:' + user[0] if user else session_id(request)


def monthly_balance(month, cap, used):
    return dict(month=month, limitKopecks=cap, usedKopecks=used,
                remainingKopecks=None if cap is None or used is None else max(0, cap-used))


def monthly_fields(balance):
    cap, remaining = balance['limitKopecks'], balance['remainingKopecks']
    return dict(monthlyLimitKopecks=cap, monthlyRemainingKopecks=remaining,
                monthlyBalanceStatus='known' if remaining is not None else 'assumed_full' if cap is not None else 'not_set')


def optional_money(value):
    return value is None or type(value) is int and 0 <= value <= 10**12


def save_usage(db, owner, card, month, used, *, catalog=False):
    table = 'catalog_monthly_usage' if catalog else 'monthly_usage'
    if used is None:
        db.execute(f'DELETE FROM {table} WHERE owner=? AND card_id=? AND month=?', (owner, card, month))
    else:
        db.execute(f'''INSERT INTO {table} (owner, card_id, month, used) VALUES (?, ?, ?, ?)
                      ON CONFLICT(owner, card_id, month) DO UPDATE SET used=excluded.used''', (owner, card, month, used))


def guest_cookie(response, request, owner):
    if not owner.startswith('account:'):
        response.set_cookie(COOKIE, owner, httponly=True, samesite='strict', max_age=31536000,
                            secure=request.url.scheme == 'https')


def create_app(db_path):
    @asynccontextmanager
    async def lifespan(app):
        app.state.html = PAGE.read_bytes()
        initialize(db_path)
        yield

    app = FastAPI(title='Советник', lifespan=lifespan)

    mount_accounts(app, db_path, session_id)
    mount_observability(app)

    @app.get('/')
    def home():
        return HTMLResponse(app.state.html, headers={'Cache-Control': 'no-store'})

    @app.get('/healthz')
    def health():
        with connect(db_path) as db:
            db.execute('SELECT 1 FROM rules LIMIT 1').fetchone()
        status = {'status': 'ok'}
        if re.fullmatch(r'[0-9a-f]{40}', BUILD_REVISION):
            status['revision'] = BUILD_REVISION
        return status

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
                                              (card_owner(db, request),))]

    @app.get('/api/me/cards')
    def my_cards(request: Request):
        with connect(db_path) as db:
            return saved(db, request)

    def catalog_monthly(db, request, day):
        month = day.isoformat()[:7]
        return {card: monthly_balance(month, cap, used) for card, cap, used in db.execute('''
            SELECT s.cardId, s.monthly_limit, u.used FROM saved s LEFT JOIN catalog_monthly_usage u
              ON u.owner=s.session AND u.card_id=s.cardId AND u.month=?
            WHERE s.session=?''', (month, card_owner(db, request)))}

    @app.get('/api/me/catalog-monthly')
    def get_catalog_monthly(request: Request):
        with connect(db_path) as db:
            db.execute('BEGIN')
            return catalog_monthly(db, request, datetime.now(UTC).date())

    def manual_cards(db, request, day):
        month = day.isoformat()[:7]
        def display_rule(rule, updated):
            label = rule.get('categoryName') or CATEGORIES[rule['categoryId']]
            return {**rule, 'categoryName': label, 'categoryKey': label.casefold(),
                    'minAmountKopecks': rule.get('minAmountKopecks', 0),
                    'validFrom': rule.get('validFrom', updated),
                    'validUntilExclusive': rule.get('validUntilExclusive'), 'updatedOn': updated}

        return [dict(cardId=card, name=name, bankName=bank, updatedOn=updated,
                     monthly=monthly_balance(month, cap, used),
                     rules=[display_rule(rule, updated) for rule in json.loads(rules)])
                for card, name, bank, updated, rules, cap, used in db.execute('''
                    SELECT c.card_id, c.name, c.bank_name, c.updated_on, c.rules_json, c.monthly_limit, u.used
                    FROM manual_cards c LEFT JOIN monthly_usage u
                    ON u.owner=c.session AND u.card_id=c.card_id AND u.month=?
                    WHERE c.session=? ORDER BY c.rowid''', (month, card_owner(db, request))) ]

    @app.get('/api/me/manual-cards')
    def list_manual_cards(request: Request, categoryName: str | None = None):
        with connect(db_path) as db:
            db.execute('BEGIN')
            cards = manual_cards(db, request, datetime.now(UTC).date())
        if categoryName is None:
            return cards
        key = category_label(categoryName).casefold()
        return [card for card in cards if any(rule['categoryKey'] == key for rule in card['rules'])]

    @app.post('/api/me/manual-cards', status_code=201)
    def create_manual_card(body: dict, request: Request):
        name, rules = category_label(body.get('name')), body.get('rules')
        bank = category_label(body.get('bankName'))
        cap, used = body.get('monthlyLimitKopecks'), body.get('monthlyUsedKopecks')
        if not optional_money(cap) or not optional_money(used):
            return JSONResponse({'code': 'invalid_monthly_amount'}, 422)
        if not 1 <= len(name) <= 80:
            return JSONResponse({'code': 'invalid_name'}, 422)
        if 'bankName' in body and not 1 <= len(bank) <= 80:
            return JSONResponse({'code': 'invalid_bank'}, 422)
        if not isinstance(rules, list) or not rules:
            return JSONResponse({'code': 'invalid_rules'}, 422)
        cleaned, seen = [], set()
        today = datetime.now(UTC).date().isoformat()
        def rule_error(index, field, code):
            return JSONResponse({'code': code, 'field': field, 'ruleIndex': index}, 422)

        for index, rule in enumerate(rules):
            if not isinstance(rule, dict):
                return JSONResponse({'code': 'invalid_rules'}, 422)
            category, rate, limit = rule.get('categoryId'), rule.get('rateBps'), rule.get('limitKopecks')
            label = category_label(rule['categoryName']) if 'categoryName' in rule else (
                CATEGORIES.get(category, '') if isinstance(category, str) else '')
            key = label.casefold()
            minimum = rule.get('minAmountKopecks', 0)
            start = rule.get('validFrom', today)
            end = rule.get('validUntilExclusive')
            if not 1 <= len(label) <= 80:
                return rule_error(index, 'categoryName', 'invalid_category')
            if key in seen:
                return rule_error(index, 'categoryName', 'duplicate_category')
            if type(rate) is not int or not 0 <= rate <= 10000:
                return rule_error(index, 'rateBps', 'invalid_rate')
            if type(minimum) is not int or not 0 <= minimum <= 10**12:
                return rule_error(index, 'minAmountKopecks', 'invalid_minimum')
            if limit is not None and (type(limit) is not int or not 0 <= limit <= 10**12):
                return rule_error(index, 'limitKopecks', 'invalid_limit')
            if not iso_day(start):
                return rule_error(index, 'validFrom', 'invalid_date')
            if end is not None:
                if not iso_day(end):
                    return rule_error(index, 'validUntilExclusive', 'invalid_date')
                if end <= start:
                    return rule_error(index, 'validUntilExclusive', 'invalid_period')
            seen.add(key)
            cleaned.append(dict(categoryId=category if 'categoryName' not in rule else key,
                                categoryName=label, rateBps=rate, limitKopecks=limit,
                                minAmountKopecks=minimum, validFrom=start, validUntilExclusive=end))
        card = 'manual-' + secrets.token_hex(12)
        with connect(db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            session = card_owner(db, request) or secrets.token_urlsafe(32)
            db.execute('INSERT INTO manual_cards (session, card_id, name, bank_name, updated_on, rules_json, monthly_limit) VALUES (?, ?, ?, ?, ?, ?, ?)',
                       (session, card, name, bank, today, json.dumps(cleaned), cap))
            if used is not None:
                save_usage(db, session, card, today[:7], used)
        response = JSONResponse({'cardId': card}, 201)
        guest_cookie(response, request, session)
        return response

    def update_limit(card, body, request, *, catalog):
        cap, used = body.get('limitKopecks'), body.get('usedKopecks')
        if not {'limitKopecks', 'usedKopecks'} <= body.keys() or not optional_money(cap) or not optional_money(used):
            return JSONResponse({'code': 'invalid_monthly_amount'}, 422)
        with connect(db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            month = datetime.now(UTC).date().isoformat()[:7]
            if body.get('month') != month:
                return JSONResponse({'code': 'month_changed'}, 409)
            owner = card_owner(db, request)
            query = ('UPDATE saved SET monthly_limit=? WHERE session=? AND cardId=?' if catalog else
                     'UPDATE manual_cards SET monthly_limit=? WHERE session=? AND card_id=?')
            result = db.execute(query, (cap, owner, card))
            if not result.rowcount:
                return JSONResponse({'code': 'unknown_card'}, 404)
            save_usage(db, owner, card, month, used, catalog=catalog)
        return Response(status_code=204)

    @app.put('/api/me/manual-cards/{card}/monthly-limit', status_code=204)
    def update_monthly_limit(card: str, body: dict, request: Request):
        return update_limit(card, body, request, catalog=False)

    @app.put('/api/me/cards/{card}/monthly-limit', status_code=204)
    def update_catalog_limit(card: str, body: dict, request: Request):
        return update_limit(card, body, request, catalog=True)

    @app.delete('/api/me/manual-cards/{card}', status_code=204)
    def delete_manual_card(card: str, request: Request):
        with connect(db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM manual_cards WHERE session = ? AND card_id = ?', (card_owner(db, request), card))
        return Response(status_code=204)

    @app.put('/api/me/cards/{card}', status_code=204)
    def add_card(card: str, request: Request):
        with connect(db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            session = card_owner(db, request) or secrets.token_urlsafe(32)
            if not db.execute('SELECT 1 FROM rules WHERE cardId = ? LIMIT 1', (card,)).fetchone():
                return JSONResponse({'code': 'unknown_card'}, 404)
            db.execute('INSERT OR IGNORE INTO saved (session, cardId) VALUES (?, ?)', (session, card))
        response = Response(status_code=204)
        guest_cookie(response, request, session)
        return response

    @app.delete('/api/me/cards/{card}', status_code=204)
    def remove_card(card: str, request: Request):
        with connect(db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM saved WHERE session = ? AND cardId = ?', (card_owner(db, request), card))
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
        day = datetime.now(UTC).date()
        with connect(db_path) as db:
            db.execute('BEGIN')
            catalog_rules = [] if scope == 'manual' else rows(db)
            personal_caps = catalog_monthly(db, request, day) if scope == 'mine' else {}
            rules = [{**rule, **monthly_fields(personal_caps[rule['cardId']])}
                     if rule['cardId'] in personal_caps else rule for rule in catalog_rules]
            own = None if scope == 'all' else set(personal_caps)
            if own is not None:
                for card in manual_cards(db, request, day):
                    own.add(card['cardId'])
                    for rule in card['rules']:
                        key = rule['categoryKey']
                        category_id = key if scope == 'manual' else CATEGORY_IDS.get(key, f'manual:{key}')
                        rules.append({**rule, 'categoryId': category_id,
                                      'cardId': card['cardId'], 'cardName': card['name'],
                                      'bankName': card['bankName'] or 'Банк не указан',
                                      **monthly_fields(card['monthly'])})
        result = recommend(category, amount, day, rules, own)
        if scope == 'mine' and not any(card['cashbackKopecks'] > 0 for card in result['top3']):
            unowned = {rule['cardId'] for rule in catalog_rules} - own
            alternatives = recommend(category, amount, day, catalog_rules, unowned)['top3']
            if alternatives and alternatives[0]['cashbackKopecks'] > 0:
                result['catalogSuggestion'] = alternatives[0]
        return result

    def spending_cards(db, request, day, category, amount):
        key = category.casefold()
        category_id = CATEGORY_IDS.get(key)
        personal = manual_cards(db, request, day)
        used_catalog_ids = set(saved(db, request))
        names = {c['cardId']: c['name'] for c in personal}
        caps = {c['cardId']: c['monthly']['limitKopecks'] for c in personal}
        caps.update({card: balance['limitKopecks'] for card, balance in catalog_monthly(db, request, day).items()})
        candidates = []
        for card in personal:
            for rule in card['rules']:
                if rule['categoryKey'] == key or (category_id and CATEGORY_IDS.get(rule['categoryKey']) == category_id):
                    candidates.append({**rule, 'cardId':card['cardId'], 'cardName':card['name'], 'categoryId':key})
        for rule in rows(db):
            if rule['cardId'] in used_catalog_ids:
                card_id = rule['cardId']
                names[card_id] = card_info(card_id)['cardName']
                if rule['categoryId'] == category_id:
                    candidates.append({**rule, 'categoryId':key})
        estimates = {}
        for match in recommend(key, amount, day, candidates)['allMatches']:
            card_id = match['cardId']
            if card_id not in estimates and match['cashbackKopecks'] > 0:
                estimates[card_id] = dict(cardId=card_id, name=match['cardName'],
                    cashbackKopecks=match['cashbackKopecks'], monthlyCapKopecks=caps.get(card_id))
        return names, list(estimates.values())

    mount_spending(app, db_path, lambda: datetime.now(UTC).date(), category_label, iso_day, spending_cards)
    return app


app = create_app(Path(os.environ.get('ADVISOR_DB', 'advisor.sqlite3')))
