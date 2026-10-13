import unittest
from src.money import split_cents

class HoldoutTests(unittest.TestCase):
    def test_conservation_and_fairness(self):
        for total in [0, 1, 2, 7, 101, 999, 10001]:
            for people in [1, 2, 3, 8, 12]:
                shares = split_cents(total, people)
                self.assertEqual(len(shares), people)
                self.assertEqual(sum(shares), total)
                self.assertLessEqual(max(shares) - min(shares), 1)
                self.assertEqual(shares, sorted(shares, reverse=True))

    def test_invalid_count(self):
        for people in [0, -1, True, 2.5]:
            with self.assertRaises(ValueError):
                split_cents(100, people)

    def test_invalid_amount(self):
        for amount in [-1, True, 1.5]:
            with self.assertRaises(ValueError):
                split_cents(amount, 3)
