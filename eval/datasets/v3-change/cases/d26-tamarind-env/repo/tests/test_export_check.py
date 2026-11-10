import unittest


class ExportCheckTests(unittest.TestCase):
    def test_environment_mapping_available(self):
        import os
        self.assertIsNotNone(os.environ)


if __name__ == "__main__":
    unittest.main()
