import argparse
import json
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

CATEGORIES = {
    'supermarkets': 'Супермаркеты', 'cafe': 'Кафе', 'fuel': 'АЗС',
    'pharmacy': 'Аптеки', 'transport': 'Транспорт', 'clothing': 'Одежда',
    'electronics': 'Электроника', 'marketplace': 'Маркетплейсы',
    'entertainment': 'Развлечения', 'utilities': 'Связь и ЖКХ',
    'travel': 'Путешествия', 'all': 'Все покупки',
}
BANKS = (
    ('sber', 'СберБанк', '#0C8C50', '#FFFFFF', ''),
    ('vtb', 'ВТБ', '#0050D8', '#FFFFFF', ''),
    ('gazprombank', 'Газпромбанк', '#122C68', '#FFFFFF', ''),
    ('alfabank', 'Альфа-Банк', '#E52030', '#FFFFFF', ''),
    ('rshb', 'Россельхозбанк', '#225735', '#FFFFFF', ''),
    ('domrf', 'Банк ДОМ.РФ', '#24282C', '#FFFFFF', ''),
    ('tbank', 'Т-Банк', '#191919', '#FFFFFF', '#FFDD2D'),
    ('mkb', 'Московский Кредитный Банк (МКБ)', '#8B2142', '#FFFFFF', ''),
    ('sovcombank', 'Совкомбанк', '#007CB5', '#FFFFFF', ''),
    ('raiffeisen', 'Райффайзенбанк', '#FEE600', '#161616', ''),
    ('novikom', 'Новиком', '#40377C', '#FFFFFF', ''),
    ('rossiya', 'Банк «Россия»', '#84252E', '#FFFFFF', ''),
    ('rencap', 'РенКап Банк', '#642B65', '#FFFFFF', ''),
    ('bspb', 'Банк «Санкт-Петербург»', '#BF2350', '#FFFFFF', ''),
    ('akbars', 'Ак Барс Банк', '#007D6A', '#FFFFFF', ''),
    ('ozon', 'Ozon Банк', '#005BFF', '#FFFFFF', ''),
    ('otp', 'ОТП Банк', '#A8D500', '#161616', ''),
    ('uralsib', 'Уралсиб', '#2846A0', '#FFFFFF', ''),
    ('mts', 'МТС Банк', '#E30613', '#FFFFFF', ''),
    ('unicredit', 'ЮниКредит Банк', '#D8DCE3', '#161616', ''),
)


def bank_names():
    return {bank[0]: bank[1] for bank in BANKS}


def bank_public():
    return [{'id': bank[0], 'name': bank[1], 'color': bank[2], 'ink': bank[3], 'accent': bank[4]}
            for bank in BANKS]
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
        CREATE TABLE IF NOT EXISTS saved (
          session TEXT, cardId TEXT, PRIMARY KEY(session, cardId)
        );
        CREATE TABLE IF NOT EXISTS users (
          session TEXT PRIMARY KEY, login TEXT NOT NULL UNIQUE,
          password_hash TEXT NOT NULL, created_on TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS manual_cards (
          session TEXT NOT NULL, card_id TEXT NOT NULL, name TEXT NOT NULL,
          updated_on TEXT NOT NULL, rules_json TEXT NOT NULL,
          PRIMARY KEY(session, card_id)
        );
        CREATE TABLE IF NOT EXISTS purchases (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session TEXT NOT NULL, bought_on TEXT NOT NULL, category_id TEXT NOT NULL,
          amount_kopecks INTEGER NOT NULL,
          recommended_card TEXT NOT NULL, recommended_name TEXT NOT NULL, recommended_kopecks INTEGER NOT NULL,
          chosen_card TEXT NOT NULL, chosen_name TEXT NOT NULL, chosen_kopecks INTEGER NOT NULL,
          usual_kopecks INTEGER, catalog_version TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS usual_card (
          session TEXT PRIMARY KEY, card_id TEXT NOT NULL
        );
    ''')
    columns = {row[1] for row in db.execute('PRAGMA table_info(users)')}
    if 'password_hash' not in columns:
        db.execute('DROP TABLE users')
        db.execute('''CREATE TABLE users (
          session TEXT PRIMARY KEY, login TEXT NOT NULL UNIQUE,
          password_hash TEXT NOT NULL, created_on TEXT NOT NULL
        )''')


def rows(db):
    return [dict(zip(FIELDS, row)) for row in db.execute('SELECT * FROM rules ORDER BY cardId, categoryId, validFrom')]


def apply_rules(db, items):
    seen = set()
    for rule in items:
        if not isinstance(rule, dict) or set(rule) != set(FIELDS):
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
        db.execute('INSERT OR REPLACE INTO rules VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (c,k,r,l,m,start,end,updated))
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
