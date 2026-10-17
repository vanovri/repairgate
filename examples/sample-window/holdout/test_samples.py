import itertools
import unittest
from src.samples import moving_average


class SampleRegressions(unittest.TestCase):
    def test_synthetic_sequences_against_reference(self):
        for length in range(5):
            for values in itertools.product([-3, 0, 7], repeat=length):
                for window in [1, 2, 3, 8]:
                    source = list(values)
                    with self.subTest(source=source, window=window):
                        actual = moving_average(source, window)
                        self.assertEqual(len(actual), len(source))
                        self.assertEqual(source, list(values))
                        for i, mean in enumerate(actual):
                            segment = source[max(0, i-window+1):i+1]
                            self.assertAlmostEqual(mean, sum(segment) / len(segment))

    def test_invalid_window(self):
        for window in [0, -1, True, 1.5, '2', None]:
            with self.subTest(window=window), self.assertRaises(ValueError):
                moving_average([2, 4], window)

    def test_invalid_samples(self):
        for source in [None, '24', [True], [False], [1.5], ['2'], [None]]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                moving_average(source, 2)
