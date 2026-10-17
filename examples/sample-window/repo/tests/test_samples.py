import unittest
from src.samples import moving_average


class VisibleSamples(unittest.TestCase):
    def test_startup_window(self):
        self.assertEqual(moving_average([2, 4, 6], 2), [2.0, 3.0, 5.0])

    def test_one_sample_window(self):
        self.assertEqual(moving_average([3, 6], 1), [3.0, 6.0])
