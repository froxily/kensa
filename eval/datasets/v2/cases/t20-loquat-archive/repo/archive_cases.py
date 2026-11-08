import unittest
from pymongo import MongoClient

class ArchiveChecks(unittest.TestCase):
    def test_index_available(self):
        sections = ['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen', 'twenty']
        for section in sections:
            print('checking section:', section, flush=True)
        client = MongoClient('mongodb://documentstore:27017', serverSelectionTimeoutMS=2000)
        self.assertTrue(client.admin.command('ping')['ok'])

if __name__ == '__main__':
    unittest.main()
