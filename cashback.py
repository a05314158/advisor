import os, re, json, base64
from pathlib import Path
import httpx
from catalog import CATEGORIES

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


