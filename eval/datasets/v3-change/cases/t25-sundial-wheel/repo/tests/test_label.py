import unittest
from sundial import label

class LabelTest(unittest.TestCase):
    def test_hour_label(self):
        self.assertEqual(label(4), "hour-4")
