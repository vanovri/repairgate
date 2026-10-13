import unittest
from src.money import split_cents

class SplitTests(unittest.TestCase):
    def test_remainder(self):
        self.assertEqual(split_cents(100, 3), [34, 33, 33])

    def test_even_split(self):
        self.assertEqual(split_cents(90, 3), [30, 30, 30])
