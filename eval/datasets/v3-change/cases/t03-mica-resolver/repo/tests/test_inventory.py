import unittest
from src.inventory import object_key

class InventoryKeyTests(unittest.TestCase):
    def test_joins_namespace_and_name(self):
        self.assertEqual(object_key("north", "crate"), "north/crate")
