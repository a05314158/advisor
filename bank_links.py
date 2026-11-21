"""Public bank entry points for supported issuers."""
from unicodedata import normalize


BANK_ACCESS = {
    'sber': {'id': 'sber', 'name': 'СберБанк Онлайн', 'webUrl': 'https://online.sberbank.ru/'},
    'vtb': {'id': 'vtb', 'name': 'ВТБ Онлайн', 'webUrl': 'https://online.vtb.ru/'},
    'tbank': {'id': 'tbank', 'name': 'Т‑Банк', 'webUrl': 'https://www.tbank.ru/login/'},
    'alfa': {'id': 'alfa', 'name': 'Альфа‑Банк', 'webUrl': 'https://web.alfabank.ru/'},
}
ALIASES = {
    'сбер': 'sber', 'сбербанк': 'sber', 'sberbank': 'sber',
    'втб': 'vtb', 'банквтб': 'vtb', 'vtb': 'vtb',
    'тбанк': 'tbank',
    'tbank': 'tbank',
    'тинькофф': 'tbank',
    'тинькоффбанк': 'tbank',
    'tinkoff': 'tbank',
    'tinkoffbank': 'tbank',
    'альфа': 'alfa',
    'альфабанк': 'alfa',
    'alfabank': 'alfa',
}


def bank_access(name):
    # Keep the lookup exact after normalizing common typography and spacing.
    key = ''.join(char for char in normalize('NFKC', name).casefold()
                  if not (char.isspace() or char in '-‐‑‒–—−'))
    return BANK_ACCESS.get(ALIASES.get(key))
