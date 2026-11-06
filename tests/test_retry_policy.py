import unittest
from unittest.mock import Mock
import requests
from requests.exceptions import HTTPError
from scrape_worker import is_retryable_error

class RetryPolicyTests(unittest.TestCase):
    def test_retries_transport_failures(self):
        self.assertTrue(is_retryable_error(requests.exceptions.Timeout()))
        self.assertTrue(is_retryable_error(requests.exceptions.ConnectionError()))
    def test_retries_only_retryable_http_statuses(self):
        for status in (429, 500, 502, 503, 504):
            self.assertTrue(is_retryable_error(HTTPError(response=Mock(status_code=status))), status)
        for status in (400, 401, 403, 404):
            self.assertFalse(is_retryable_error(HTTPError(response=Mock(status_code=status))), status)
    def test_does_not_retry_parser_errors(self):
        self.assertFalse(is_retryable_error(ValueError('invalid merchant payload')))

if __name__ == '__main__':
    unittest.main()
