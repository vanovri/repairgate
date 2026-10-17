import unittest
from src.intervals import merge_intervals


class VisibleIntervals(unittest.TestCase):
    def test_touching_intervals(self):
        self.assertEqual(merge_intervals([(1, 3), (3, 5)]), [(1, 5)])

    def test_disjoint_intervals(self):
        self.assertEqual(merge_intervals([(0, 1), (3, 4)]), [(0, 1), (3, 4)])
