import unittest

from fjord_window import active_slots


class WindowCountTests(unittest.TestCase):
    def test_half_open_window(self):
        self.assertEqual(active_slots(3, 7), 4)

    def test_empty_window(self):
        self.assertEqual(active_slots(5, 5), 0)


if __name__ == "__main__":
    unittest.main()
