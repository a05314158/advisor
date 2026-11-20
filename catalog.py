import argparse
import json
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from unicodedata import category, normalize

CATEGORY_GROUPS = {
    'Еда и покупки': {
        'supermarkets': 'Супермаркеты', 'groceries': 'Продукты', 'cafe': 'Кафе',
        'fast_food': 'Фастфуд', 'marketplaces': 'Маркетплейсы', 'alcohol': 'Алкоголь',
    },
    'Повседневные расходы и дом': {
        'pharmacies': 'Аптеки', 'clothes': 'Одежда и обувь', 'home': 'Дом и ремонт',
        'pets': 'Животные', 'books': 'Книги', 'flowers': 'Цветы', 'kids': 'Детские товары',
    },
    'Дорога и поездки': {
        'fuel': 'АЗС', 'taxi': 'Такси', 'car_sharing': 'Каршеринг', 'transport': 'Транспорт',
        'tickets': 'Авиа- и ж/д билеты', 'hotels': 'Отели',
    },
    'Досуг и уход': {
        'beauty': 'Красота', 'entertainment': 'Развлечения', 'cinema': 'Кино',
        'sports': 'Спорттовары и тренировки', 'subscriptions': 'Подписки', 'digital': 'Цифровые товары',
    },
}
CATEGORIES = {category_id: label for group in CATEGORY_GROUPS.values() for category_id, label in group.items()}
SEED = [dict(cardId=c, categoryId=k, rateBps=r, limitKopecks=l, minAmountKopecks=m,
             validFrom='2026-11-01', validUntilExclusive='2027-11-01', updatedOn='2026-11-01')
        for c,k,r,l,m in [('A','supermarkets',1000,10000,1), ('B','supermarkets',600,30000,1),
                          ('C','supermarkets',400,20000,1), ('D','supermarkets',200,10000,1),
                          ('D','cafe',800,30000,10000)]]
FIELDS = tuple(SEED[0])


@contextmanager
def connect(path):
    db = sqlite3.connect(path)
    try:
        db.execute('PRAGMA foreign_keys = ON')
        with db:
            yield db
    finally:
        db.close()


def setup(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS rules (
          cardId TEXT, categoryId TEXT, rateBps INTEGER, limitKopecks INTEGER,
          minAmountKopecks INTEGER, validFrom TEXT, validUntilExclusive TEXT, updatedOn TEXT,
          PRIMARY KEY (cardId, categoryId, validFrom)
        );
        CREATE TABLE IF NOT EXISTS catalog_cards (
          id TEXT PRIMARY KEY, bank_name TEXT NOT NULL, name TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS saved (
          session TEXT, cardId TEXT, PRIMARY KEY(session, cardId)
        );
        CREATE TABLE IF NOT EXISTS manual_cards (
          session TEXT NOT NULL, card_id TEXT NOT NULL, name TEXT NOT NULL,
          updated_on TEXT NOT NULL, rules_json TEXT NOT NULL,
          PRIMARY KEY(session, card_id)
        );
        CREATE TABLE IF NOT EXISTS accounts (
          id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, salt BLOB NOT NULL, password_hash BLOB NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auth_sessions (
          digest BLOB PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id), expires_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS auth_sessions_expiry ON auth_sessions(expires_at);
        CREATE TABLE IF NOT EXISTS monthly_usage (
          owner TEXT NOT NULL, card_id TEXT NOT NULL, month TEXT NOT NULL,
          used INTEGER NOT NULL CHECK(used BETWEEN 0 AND 1000000000000),
          PRIMARY KEY(owner, card_id, month),
          FOREIGN KEY(owner, card_id) REFERENCES manual_cards(session, card_id)
            ON UPDATE CASCADE ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS purchases (
          id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
          day TEXT NOT NULL, category TEXT NOT NULL, merchant TEXT NOT NULL,
          amount INTEGER NOT NULL CHECK(amount BETWEEN 1 AND 1000000000000),
          used_card TEXT, estimates TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS purchases_account_day ON purchases(account_id, day);
        CREATE TABLE IF NOT EXISTS purchase_cashback (
          purchase_id TEXT PRIMARY KEY REFERENCES purchases(id) ON DELETE CASCADE,
          amount INTEGER NOT NULL CHECK(amount BETWEEN 0 AND 1000000000000)
        );
        CREATE TABLE IF NOT EXISTS purchase_requests (
          account_id TEXT NOT NULL REFERENCES accounts(id), request_key TEXT NOT NULL,
          payload_digest TEXT NOT NULL, purchase_id TEXT NOT NULL,
          PRIMARY KEY(account_id, request_key)
        );
        CREATE TABLE IF NOT EXISTS catalog_monthly_usage (
          owner TEXT NOT NULL, card_id TEXT NOT NULL, month TEXT NOT NULL,
          used INTEGER NOT NULL CHECK(used BETWEEN 0 AND 1000000000000),
          PRIMARY KEY(owner, card_id, month),
          FOREIGN KEY(owner, card_id) REFERENCES saved(session, cardId)
            ON UPDATE CASCADE ON DELETE CASCADE
        );
    ''')
    db.execute('BEGIN IMMEDIATE')
    columns = {col[1] for col in db.execute('PRAGMA table_info(manual_cards)')}
    if 'bank_name' not in columns:
        db.execute("ALTER TABLE manual_cards ADD COLUMN bank_name TEXT NOT NULL DEFAULT ''")
    if 'monthly_limit' not in columns:
        db.execute('ALTER TABLE manual_cards ADD COLUMN monthly_limit INTEGER CHECK(monthly_limit BETWEEN 0 AND 1000000000000)')
    if not any(col[1] == 'monthly_limit' for col in db.execute('PRAGMA table_info(saved)')):
        db.execute('ALTER TABLE saved ADD COLUMN monthly_limit INTEGER CHECK(monthly_limit BETWEEN 0 AND 1000000000000)')
    db.commit()


def rows(db):
    result = []
    for *values, bank, name in db.execute('''SELECT r.cardId, r.categoryId, r.rateBps, r.limitKopecks,
        r.minAmountKopecks, r.validFrom, r.validUntilExclusive, r.updatedOn, c.bank_name, c.name
        FROM rules r LEFT JOIN catalog_cards c ON c.id=r.cardId
        ORDER BY r.cardId, r.categoryId, r.validFrom'''):
        rule = dict(zip(FIELDS, values))
        if bank is not None:
            rule.update(bankName=bank, cardName=name)
        result.append(rule)
    return result


def catalog_label(value):
    if not isinstance(value, str) or any(category(char) in {'Cc', 'Cf', 'Cs'} for char in value):
        raise ValueError('Неверное название банка или карты')
    clean = ' '.join(normalize('NFC', value).split())
    if not 1 <= len(clean) <= 80:
        raise ValueError('Неверное название банка или карты')
    return clean


def apply_rules(db, items):
    seen, names = set(), {}
    metadata_fields = {'bankName', 'cardName'}
    fields = set(FIELDS)
    for rule in items:
        if not isinstance(rule, dict) or set(rule) not in (fields, fields | metadata_fields):
            raise ValueError('Неверные поля условия')
        c, k, r, l, m, start, end, updated = (rule[f] for f in FIELDS)
        if (not isinstance(c, str) or not c.isascii() or not c.isalnum() or len(c) > 32
                or not isinstance(k, str) or k not in CATEGORIES
                or any(type(n) is not int for n in (r, l, m))
                or not (0 <= r <= 10000 and 0 <= l <= 10**12 and 1 <= m <= 10**12)):
            raise ValueError('Неверные значения условия')
        for d in (start, end, updated):
            if not isinstance(d, str) or date.fromisoformat(d).isoformat() != d:
                raise ValueError('Ожидается дата YYYY-MM-DD')
        if start >= end or (c, k, start) in seen:
            raise ValueError('Пустой период или повтор правила в пакете')
        seen.add((c, k, start))
        if metadata_fields <= rule.keys():
            metadata = catalog_label(rule['bankName']), catalog_label(rule['cardName'])
            if names.setdefault(c, metadata) != metadata:
                raise ValueError(f'Несогласованные названия для карты: {c}')
        db.execute('INSERT OR REPLACE INTO rules VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (c,k,r,l,m,start,end,updated))
    db.executemany('''INSERT INTO catalog_cards (id, bank_name, name) VALUES (?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET bank_name=excluded.bank_name, name=excluded.name''',
        ((card, bank, name) for card, (bank, name) in names.items()))
    previous = None
    for rule in rows(db):
        key = rule['cardId'], rule['categoryId']
        if previous and previous[0] == key and rule['validFrom'] < previous[1]:
            raise ValueError(f'Пересекающиеся периоды: {key}')
        previous = key, rule['validUntilExclusive']


def import_catalog(path, items):
    with connect(path) as db:
        setup(db)
        db.execute('BEGIN IMMEDIATE')
        apply_rules(db, items)


def initialize(path):
    with connect(path) as db:
        setup(db)
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM rules LIMIT 1').fetchone():
            apply_rules(db, SEED)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Импорт учебных условий (JSON-массив правил)')
    parser.add_argument('file', type=Path)
    parser.add_argument('--db', type=Path, default=Path('advisor.sqlite3'))
    args = parser.parse_args()
    try:
        items = json.loads(args.file.read_text(encoding='utf-8'))
        if not isinstance(items, list) or not items:
            raise ValueError('Нужен непустой JSON-массив')
        import_catalog(args.db, items)
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f'Импорт не выполнен: {exc}\n')
    print(f'Импортировано правил: {len(items)}')
