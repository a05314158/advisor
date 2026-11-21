import unittest
from datetime import date

from advisor import recommend


class Calculation(unittest.TestCase):
    def query(self, category='supermarkets', amount=250000, day='2026-11-20'):
        return recommend(category, amount, date.fromisoformat(day))

    def test_supermarkets(self):
        result = self.query()
        self.assertEqual([(x['cardId'], x['cashbackKopecks']) for x in result['allMatches']],
                         [('B', 15000), ('A', 10000), ('C', 10000), ('D', 5000)])
        self.assertEqual(result['top3'], result['allMatches'][:3])
        self.assertTrue(result['top3'][1]['limitApplied'])

    def test_rounding(self):
        self.assertEqual(self.query(amount=105)['top3'][0]['cashbackKopecks'], 11)

    def test_category_and_minimum(self):
        self.assertEqual(self.query('cafe')['top3'][0]['cashbackKopecks'], 20000)
        self.assertEqual(self.query('cafe', 9999)['top3'], [])
        self.assertEqual(self.query('fuel')['top3'], [])

    def test_dates(self):
        self.assertTrue(self.query(day='2026-11-01')['top3'])
        self.assertFalse(self.query(day='2027-11-01')['top3'])

    def test_explanation_keeps_each_limit_stage_and_rounding(self):
        from catalog import SEED

        rule = dict(SEED[0], monthlyLimitKopecks=30000, monthlyRemainingKopecks=8000)
        result = recommend('supermarkets', 250000, date(2026, 11, 20), [rule])['top3'][0]
        self.assertEqual(result['calculation'], dict(amountKopecks=250000,
                         beforeLimitsKopecks=25000, afterCategoryLimitKopecks=10000))
        self.assertEqual(result['cashbackKopecks'], 8000)
        self.assertTrue(result['limitApplied'])
        self.assertTrue(result['monthlyLimitApplied'])
        match = self.query(amount=105)['top3'][0]
        self.assertEqual(match['calculation']['beforeLimitsKopecks'], 11)
        self.assertEqual(match['cashbackKopecks'], 11)
