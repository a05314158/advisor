import unittest
import os
import tempfile
from pathlib import Path
from datetime import UTC, datetime
from unittest.mock import patch

from fastapi.testclient import TestClient
from httpx import Response

from advisor import create_app


class RecommendationsAPI(unittest.TestCase):
    def setUp(self):
        clock = self.enterContext(patch('advisor.datetime'))
        clock.now.return_value = datetime(2026, 11, 20, tzinfo=UTC)
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.client = self.enterContext(TestClient(create_app(Path(directory) / 'test.db')))

    def request(self, **overrides):
        payload = dict(categoryId='supermarkets', amountKopecks=250000, scope='all')
        payload.update(overrides)
        return self.client.post('/api/recommendations', json=payload)

    def test_screen_is_served(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response.headers['content-type'])
        self.assertIn('/api/recommendations', response.text)

    def test_ranking_details_and_repeatability(self):
        response = self.request()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['asOf'], '2026-11-20')
        self.assertEqual(data['catalogVersion'], 'training-v1')
        self.assertEqual([(x['cardId'], x['cashbackKopecks']) for x in data['top3']],
                         [('B', 15000), ('A', 10000), ('C', 10000)])
        self.assertEqual([x['cardId'] for x in data['allMatches']], ['B', 'A', 'C', 'D'])
        capped = data['top3'][1]
        self.assertTrue(capped['limitApplied'])
        self.assertEqual(capped['limitKopecks'], 10000)
        self.assertEqual(capped['updatedOn'], '2026-11-01')
        self.assertEqual(self.request().json(), data)

    def test_cafe_changes_winner(self):
        response = self.request(categoryId='cafe')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([(x['cardId'], x['cashbackKopecks']) for x in response.json()['top3']],
                         [('D', 20000)])

    def test_empty_category_is_not_an_error(self):
        response = self.request(categoryId='fuel')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['top3'], [])
        self.assertEqual(response.json()['allMatches'], [])

    def test_invalid_amounts(self):
        for amount in (0, -1, 2.5, True, '250000', None):
            with self.subTest(amount=amount):
                response = self.request(amountKopecks=amount)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json(),
                                 {'field': 'amountKopecks', 'code': 'positive_integer_required'})

    def test_unknown_category(self):
        response = self.request(categoryId='unknown')
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['field'], 'categoryId')

    def test_empty_mine_does_not_show_all_cards(self):
        response = self.request(scope='mine')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['allMatches'], [])
        self.assertEqual(response.json()['catalogSuggestion']['cardId'], 'B')

    def test_catalog_suggestion_is_separate_and_only_for_positive_cashback(self):
        self.assertEqual(self.client.put('/api/me/cards/A').status_code, 204)
        self.assertNotIn('catalogSuggestion', self.request(scope='mine').json())
        response = self.request(scope='mine', categoryId='cafe').json()
        self.assertEqual(response['top3'], [])
        self.assertEqual(response['catalogSuggestion']['cardId'], 'D')
        self.assertEqual(response['catalogSuggestion']['cashbackKopecks'], 20000)
        self.assertNotIn('catalogSuggestion', self.request(scope='mine', categoryId='cafe', amountKopecks=5000).json())
        self.assertNotIn('catalogSuggestion', self.request(scope='mine', categoryId='clothes').json())

    def test_category_picker_includes_categories_without_catalog_rules(self):
        groups = self.client.get('/api/category-groups').json()
        self.assertEqual(groups['Еда и покупки']['groceries'], 'Продукты')
        self.assertEqual(groups['Повседневные расходы и дом']['clothes'], 'Одежда и обувь')
        response = self.request(categoryId='groceries')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['top3'], [])

    def test_mine_combines_catalog_and_named_manual_category(self):
        self.assertEqual(self.client.put('/api/me/cards/A').status_code, 204)
        personal = self.client.post('/api/me/manual-cards', json={
            'name': 'Моя карта',
            'rules': [{'categoryName': '  СУПЕРМАРКЕТЫ  ', 'rateBps': 800}],
        })
        self.assertEqual(personal.status_code, 201)
        results = self.request(scope='mine').json()['allMatches']
        self.assertEqual([(item['cardName'], item['cashbackKopecks']) for item in results],
                         [('Моя карта', 20000), ('Карта A', 10000)])

    def test_nearby_suggests_supported_rubrics_in_distance_order(self):
        payload = {'meta': {'code': 200}, 'result': {'items': [
            {'name': 'Кафе', 'point': {'lat': 55.7503, 'lon': 37.61}, 'rubrics': [{'name': 'Кафе'}]},
            {'name': 'Магазин', 'address_name': 'Учебная, 1', 'point': {'lat': 55.75, 'lon': 37.61},
             'rubrics': [{'name': 'Супермаркеты'}, {'name': 'АЗС'}]},
            {'name': 'Нотариус', 'point': {'lat': 55.75, 'lon': 37.61}, 'rubrics': [{'name': 'Нотариусы'}]},
            {'name': 'Дальний магазин', 'point': {'lat': 55.76, 'lon': 37.61},
             'rubrics': [{'name': 'Супермаркеты'}]},
        ]}}
        with patch.dict(os.environ, ADVISOR_2GIS_KEY='test-key'):
            with patch('nearby.httpx.get', return_value=Response(200, json=payload)) as lookup:
                result = self.client.post('/api/nearby', json={'latitude': 55.75, 'longitude': 37.61, 'accuracy': 20})
                places = result.json()['places']
                self.assertEqual([item['name'] for item in places], ['Магазин', 'Кафе'])
                self.assertEqual(places[0]['categoryIds'], ['fuel', 'supermarkets'])
                self.assertEqual(places[0]['address'], 'Учебная, 1')
                self.assertEqual(lookup.call_args.kwargs['params']['point'], '37.61000,55.75000')

    def test_nearby_skips_provider_for_bad_position_or_missing_key(self):
        with patch.dict(os.environ, ADVISOR_2GIS_KEY=''), patch('nearby.httpx.get') as lookup:
            location = {'latitude': 55.75, 'longitude': 37.61, 'accuracy': 250}
            self.assertEqual(self.client.post('/api/nearby', json=location).json()['status'], 'low_accuracy')
            location['accuracy'] = 20
            self.assertFalse(self.client.get('/api/nearby').json()['available'])
            self.assertEqual(self.client.post('/api/nearby', json=location).json()['status'], 'not_configured')
            location['latitude'] = 100
            self.assertEqual(self.client.post('/api/nearby', json=location).status_code, 422)
            lookup.assert_not_called()
