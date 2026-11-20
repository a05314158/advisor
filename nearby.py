from math import asin, ceil, cos, radians, sin, sqrt

import httpx

RUBRIC_CATEGORIES = {
    'супермаркеты': 'supermarkets',
    'гипермаркеты': 'supermarkets',
    'продуктовые магазины': 'groceries',
    'кафе': 'cafe',
    'рестораны': 'cafe',
    'быстрое питание': 'fast_food',
    'аптеки': 'pharmacies',
    'магазины одежды': 'clothes',
    'цветы': 'flowers',
    'отели': 'hotels',
    'гостиницы': 'hotels',
    'кинотеатры': 'cinema',
    'азс': 'fuel',
    'автозаправочные станции (азс)': 'fuel',
}
MAX_ACCURACY_METRES = 120


def within(value, lower, upper):
    return type(value) in (int, float) and lower <= value <= upper


def distance_metres(lat, lon, other_lat, other_lon):
    d_lat, d_lon = radians(other_lat - lat), radians(other_lon - lon)
    half_chord = sin(d_lat / 2)**2 + cos(radians(lat)) * cos(radians(other_lat)) * sin(d_lon / 2)**2
    return round(12742000 * asin(sqrt(min(1, half_chord))))


def search_places(key, lat, lon, accuracy):
    radius = max(55, ceil(accuracy) + 35)
    response = httpx.get('https://catalog.api.2gis.com/3.0/items', params={
        'point': f'{lon:.5f},{lat:.5f}',
        'radius': radius,
        'type': 'branch',
        'fields': 'items.point,items.rubrics',
        'page_size': 10,
        'key': key,
    }, timeout=3)
    payload = response.json() if response.status_code in (200, 404) else {}
    code = payload.get('meta', {}).get('code')
    if code == 404:
        return []
    if code != 200 or response.status_code != 200:
        raise ValueError('Places API search failed')
    matches = []
    seen = set()
    for item in payload['result']['items']:
        point = item.get('point') or {}
        item_lat, item_lon = point.get('lat'), point.get('lon')
        if not within(item_lat, -90, 90) or not within(item_lon, -180, 180):
            continue
        distance = distance_metres(lat, lon, item_lat, item_lon)
        categories = set()
        for rubric in item.get('rubrics') or ():
            label = (rubric.get('name') or '').strip().casefold()
            if label in RUBRIC_CATEGORIES:
                categories.add(RUBRIC_CATEGORIES[label])
        name, address = item.get('name'), item.get('address_name') or ''
        identity = (name, address, item_lat, item_lon)
        if not name or not categories or distance > radius or identity in seen:
            continue
        seen.add(identity)
        matches.append(dict(name=name, address=address, distanceMetres=distance, categoryIds=sorted(categories)))
    matches.sort(key=lambda item: (item['distanceMetres'], item['name']))
    return matches[:5]
