import os
import secrets
import re
import hashlib
import json
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from unicodedata import category as unicode_category, normalize

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

from catalog import CATEGORIES, CATEGORY_GROUPS, SEED, connect, initialize, rows
from accounts import account, mount_accounts
from bank_links import bank_access
from observability import mount_observability
from spending import mount_spending
from cashback import decode_image, parse_rules, month_totals, read_cashback
from catalog import bank_public, bank_names
PAGE = Path(__file__).with_name('wallet.html')
BANKS = Path(__file__).with_name('banks_ru.json')
BUILD_REVISION = '$Format:%H$'
CATEGORY_IDS = {label.casefold(): category_id for category_id, label in CATEGORIES.items()}
CATEGORY_IDS['кафе и рестораны'] = 'cafe'



def recommend(category: str, amount: int, day: date, rules=None, own=None, *, catalog_version=None) -> dict:
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
        final = cashback if monthly is None else min(cashback, monthly)
        match = {**card_info(card), **rule, 'cashbackKopecks': final,
                 'limitApplied': cap is not None and raw > cap,
                 'calculation': dict(amountKopecks=amount, beforeLimitsKopecks=raw,
                                     afterCategoryLimitKopecks=cashback)}
        if monthly is not None:
            match['monthlyLimitApplied'] = final < cashback
        matches.append(match)
    matches.sort(key=lambda x: (-x['cashbackKopecks'], x['cardId']))
    ranked = []
    seen = set()
    for match in matches:
        if match['cardId'] not in seen:
            access = bank_access(match['bankName'])
            if access is not None:
                match['bankAccess'] = access
            ranked.append(match)
            seen.add(match['cardId'])
    version = rules_version(rules) if catalog_version is None else catalog_version
    return dict(asOf=today, catalogVersion=version, top3=ranked[:3], allMatches=ranked)


def rules_version(rules):
    def canonical(items):
        return sorted(items, key=lambda r: (r['cardId'], r['categoryId'], r['validFrom']))
    snapshot = canonical(rules)
    return 'training-v1' if snapshot == canonical(SEED) else hashlib.sha256(
        json.dumps(snapshot, sort_keys=True).encode()).hexdigest()


def active(rule, today):
    return rule['validFrom'] <= today and (rule['validUntilExclusive'] is None or today < rule['validUntilExclusive'])


def card_info(card, rule=None):
    names = rule or {}
    return dict(cardId=card, bankName=names.get('bankName', f'Учебный банк {card}'),
                cardName=names.get('cardName', f'Карта {card}'))


COOKIE = 'advisor_session'


def category_label(raw):
    if not isinstance(raw, str) or any(unicode_category(char) in {'Cc', 'Cf', 'Cs'} for char in raw):
        return ''
    return ' '.join(normalize('NFC', raw).split())


def category_key(label):
    key = label.casefold()
    category_id = CATEGORY_IDS.get(key)
    return CATEGORIES[category_id].casefold() if category_id else key


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
        app.state.bank_directory = json.loads(BANKS.read_text(encoding='utf-8'))
        initialize(db_path)
        yield

    app = FastAPI(title='Советник', lifespan=lifespan)

    mount_accounts(app, db_path, session_id)
    mount_observability(app)

    @app.get('/')
    def home():
        return HTMLResponse(app.state.html, headers={'Cache-Control': 'no-store'})

    @app.get('/bank-link-test', include_in_schema=False)
    def bank_link_test():
        return FileResponse(PAGE.with_name('bank-link-test.html'), headers={'Cache-Control': 'no-store'})

    @app.get('/classic', include_in_schema=False)
    def classic():
        return FileResponse(PAGE.with_name('index.html'))

    @app.get('/welcome.html', include_in_schema=False)
    def welcome():
        return FileResponse(PAGE.with_name('welcome.html'))

    @app.get('/pocket.webp', include_in_schema=False)
    def pocket():
        return FileResponse(PAGE.with_name('pocket.webp'))

    @app.get('/api/meta')
    def meta():
        return {'banks': bank_public(), 'categories': CATEGORIES}

    @app.get('/healthz')
    def health():
        with connect(db_path) as db:
            db.execute('SELECT 1 FROM rules LIMIT 1').fetchone()
        status = {'status': 'ok'}
        if re.fullmatch(r'[0-9a-f]{40}', BUILD_REVISION):
            status['revision'] = BUILD_REVISION
        return status

    @app.get('/api/banks')
    def banks():
        return app.state.bank_directory

    @app.get('/api/categories')
    def categories():
        return CATEGORIES

    @app.get('/api/category-groups')
    def category_groups():
        return CATEGORY_GROUPS

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
                    result.setdefault(card, dict(**card_info(card, rule), rules=[]))
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
        return dict(**card_info(card, rules[0]), rules=[r for r in rules if active(r, today)])

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
            return {**rule, 'categoryName': label, 'categoryKey': category_key(label),
                    'minAmountKopecks': rule.get('minAmountKopecks', 0),
                    'validFrom': rule.get('validFrom', updated),
                    'validUntilExclusive': rule.get('validUntilExclusive'),
                    'updatedOn': rule.get('updatedOn', updated)}

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
        key = category_key(category_label(categoryName))
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
        if not isinstance(rules, list):
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
            key = category_key(label)
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

    @app.post('/api/me/cashback-screenshot', status_code=201)
    def cashback_screenshot(body: dict, request: Request):
        from cashback import httpx
        bank = bank_names().get(body.get('bankId'))
        if not bank:
            return JSONResponse({'message': 'Выберите банк из списка'}, 422)
        with connect(db_path) as db:
            if not account(db, request):
                return JSONResponse({'code': 'login_required'}, 401)
            owner = card_owner(db, request)
        try:
            rules = read_cashback(decode_image(body.get('image')))
        except ValueError:
            return JSONResponse({'message': 'Не удалось прочитать категории на снимке'}, 422)
        except (httpx.HTTPError, KeyError, TypeError, RuntimeError):
            return JSONResponse({'message': 'Не удалось разобрать категории. Попробуйте ещё раз'}, 502)
        labels = [{**rule, 'categoryName': CATEGORIES[rule['categoryId']]} for rule in rules]
        # Validate and normalize through the same creation path used by manual entry.
        response = create_manual_card({'name': bank, 'bankName': bank, 'rules': labels}, request)
        if response.status_code != 201:
            return response
        card = json.loads(response.body)['cardId']
        target = body.get('cardId')
        if target is not None:
            with connect(db_path) as db:
                db.execute('BEGIN IMMEDIATE')
                if not db.execute('SELECT 1 FROM manual_cards WHERE session=? AND card_id=?', (owner, target)).fetchone():
                    db.execute('DELETE FROM manual_cards WHERE session=? AND card_id=?', (owner, card))
                    return JSONResponse({'code': 'unknown_card'}, 404)
                db.execute('UPDATE manual_cards SET rules_json=(SELECT rules_json FROM manual_cards WHERE session=? AND card_id=?), updated_on=? WHERE session=? AND card_id=?',
                           (owner, card, datetime.now(UTC).date().isoformat(), owner, target))
                db.execute('DELETE FROM manual_cards WHERE session=? AND card_id=?', (owner, card))
            card = target
        return {'cardId': card, 'name': bank, 'rules': rules}

    @app.patch('/api/me/manual-cards/{card}/rate', status_code=204)
    def update_rate(card: str, body: dict, request: Request):
        label, rate = category_label(body.get('categoryName')), body.get('rateBps')
        if not 1 <= len(label) <= 80 or type(rate) is not int or not 0 <= rate <= 10000:
            return JSONResponse({'code': 'invalid_rate_update'}, 422)
        with connect(db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            owner = card_owner(db, request)
            row = db.execute('SELECT rules_json, updated_on FROM manual_cards WHERE session=? AND card_id=?',
                             (owner, card)).fetchone()
            if row is None:
                return JSONResponse({'code': 'unknown_card'}, 404)
            rules = json.loads(row[0])
            matching = [rule for rule in rules
                        if category_key(rule.get('categoryName') or CATEGORIES[rule['categoryId']]) == category_key(label)]
            if not matching:
                return JSONResponse({'code': 'unknown_category'}, 404)
            if len(matching) > 1:
                matching = [rule for rule in matching
                            if (rule.get('categoryName') or CATEGORIES[rule['categoryId']]).casefold() == label.casefold()]
                if len(matching) != 1:
                    return JSONResponse({'code': 'ambiguous_category'}, 409)
            if matching[0]['rateBps'] != rate:
                updated = datetime.now(UTC).date().isoformat()
                for rule in rules:
                    rule.setdefault('validFrom', row[1])
                    rule.setdefault('updatedOn', row[1])
                matching[0].update(rateBps=rate, updatedOn=updated)
                db.execute('UPDATE manual_cards SET rules_json=?, updated_on=? WHERE session=? AND card_id=?',
                           (json.dumps(rules), updated, owner, card))
        return Response(status_code=204)

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
            category = category_key(label) if 1 <= len(label) <= 80 else ''
        if not isinstance(category, str) or not category or (scope != 'manual' and category not in CATEGORIES):
            return JSONResponse({'field': 'categoryId', 'code': 'unknown_category'}, 422)
        if scope not in ('all', 'mine', 'manual'):
            return JSONResponse({'field': 'scope', 'code': 'unknown_scope'}, 422)
        day = datetime.now(UTC).date()
        with connect(db_path) as db:
            db.execute('BEGIN')
            public_rules = rows(db)
            version = rules_version(public_rules)
            catalog_rules = [] if scope == 'manual' else public_rules
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
        result = recommend(category, amount, day, rules, own, catalog_version=version)
        if scope == 'mine' and not any(card['cashbackKopecks'] > 0 for card in result['top3']):
            unowned = {rule['cardId'] for rule in catalog_rules} - own
            alternatives = recommend(category, amount, day, catalog_rules, unowned, catalog_version=version)['top3']
            if alternatives and alternatives[0]['cashbackKopecks'] > 0:
                result['catalogSuggestion'] = alternatives[0]
        return result

    def spending_cards(db, request, day, category, amount):
        key = category_key(category)
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
                names[card_id] = card_info(card_id, rule)['cardName']
                if rule['categoryId'] == category_id:
                    candidates.append({**rule, 'categoryId':key})
        estimates = [dict(cardId=match['cardId'], name=match['cardName'],
                          cashbackKopecks=match['cashbackKopecks'], monthlyCapKopecks=caps.get(match['cardId']))
                     for match in recommend(key, amount, day, candidates)['allMatches']]
        return names, estimates

    mount_spending(app, db_path, lambda: datetime.now(UTC).date(), category_label, iso_day, spending_cards)
    return app


app = create_app(Path(os.environ.get('ADVISOR_DB', 'advisor.sqlite3')))
