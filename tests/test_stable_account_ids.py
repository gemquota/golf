import unittest
from account_scheduler import partition_urls_by_account

class StableAccountIdTests(unittest.TestCase):
    def test_sparse_configured_ids_map_to_their_actual_record(self):
        cohorts, unknown = partition_urls_by_account(['known-u2', 'unknown'], {'known-u2': 'U2'}, 1, account_ids=['U2'])
        self.assertEqual(cohorts, {0: ['known-u2']})
        self.assertEqual(unknown, ['unknown'])

if __name__ == '__main__':
    unittest.main()
