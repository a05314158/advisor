import unittest

from advisor import month_totals


class MonthTotals(unittest.TestCase):
    def test_recorded_choices_against_best_and_usual(self):
        totals = month_totals([
            dict(chosenKopecks=10000, recommendedKopecks=15000, usualKopecks=8000),
            dict(chosenKopecks=5000, recommendedKopecks=5000, usualKopecks=2000),
        ])
        self.assertEqual(totals['count'], 2)
        self.assertEqual(totals['calculatedKopecks'], 15000)
        self.assertEqual(totals['recommendedKopecks'], 20000)
        self.assertEqual(totals['missedKopecks'], 5000)
        self.assertEqual(totals['versusUsualKopecks'], 5000)

    def test_without_usual_card_the_gap_stays_empty(self):
        totals = month_totals([
            dict(chosenKopecks=10000, recommendedKopecks=10000, usualKopecks=None),
        ])
        self.assertIsNone(totals['usualKopecks'])
        self.assertIsNone(totals['versusUsualKopecks'])
