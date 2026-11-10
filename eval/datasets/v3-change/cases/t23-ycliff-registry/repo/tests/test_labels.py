import unittest
from app.labels import fold_label


class LabelTests(unittest.TestCase):
    def test_trim_and_fold(self):
        self.assertEqual(fold_label("  Reed  "), "reed")
