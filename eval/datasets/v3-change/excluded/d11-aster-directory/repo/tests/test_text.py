import unittest
from aster.text import normalize

class TextTest(unittest.TestCase):
    def test_spaces(self):
        self.assertEqual(normalize(' A '), 'a')
