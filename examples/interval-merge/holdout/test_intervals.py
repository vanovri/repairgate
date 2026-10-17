import itertools
import unittest
from src.intervals import merge_intervals


class IntervalRegressions(unittest.TestCase):
    def test_unsorted_nested_and_duplicate_intervals(self):
        for source, expected in [
            ([(5, 8), (1, 4), (3, 6)], [(1, 8)]),
            ([(1, 9), (3, 4), (1, 9)], [(1, 9)]),
            ([(-5, -2), (-2, 0), (4, 4)], [(-5, 0), (4, 4)]),
            ([], []),
        ]:
            with self.subTest(source=source):
                self.assertEqual(merge_intervals(source), expected)

    def test_coverage_and_order_independence(self):
        domain = [(a, b) for a in range(-2, 3) for b in range(a, 3)]
        for pair in itertools.product(domain, repeat=2):
            source = list(pair)
            original = source.copy()
            with self.subTest(source=source):
                result = merge_intervals(source)
                self.assertEqual(source, original)
                self.assertEqual(result, merge_intervals(list(reversed(source))))
                self.assertEqual(result, merge_intervals(result))
                self.assertTrue(all(-2 <= a <= b <= 2 for a, b in result))
                self.assertTrue(all(result[i][1] < result[i+1][0] for i in range(len(result)-1)))
                for tick in range(-4, 5):
                    point = tick / 2
                    self.assertEqual(any(a <= point <= b for a, b in source),
                                     any(a <= point <= b for a, b in result))

    def test_invalid_intervals(self):
        for value in [None, '1,2', [1], [(1,)], [(1, 2, 3)], [(3, 1)],
                      [(True, 3)], [(1, False)], [(1.5, 3)], [('1', 3)]]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                merge_intervals(value)
