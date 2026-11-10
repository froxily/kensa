import unittest
from src.measure import span


class SpanTests(unittest.TestCase):
    def test_positive_span(self):
        self.assertEqual(span(3, 8), 5)
