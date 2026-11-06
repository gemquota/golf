import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import network


class NetworkResilienceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cache = Path(self.temp.name) / "nested" / "ip_health.json"
        self.patcher = patch.object(network, "CACHE_PATH", self.cache)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp.cleanup()

    def test_corrupt_cache_is_ignored_and_replaced_atomically(self):
        self.cache.parent.mkdir(parents=True)
        self.cache.write_text("{broken", encoding="utf-8")
        response = Mock()
        response.json.return_value = {
            "data": {"abuseConfidenceScore": 12, "ipAddress": "203.0.113.9"}
        }
        response.raise_for_status.return_value = None
        with patch.object(network.requests, "get", return_value=response) as get:
            self.assertEqual(network.check_ip_reputation("test-key"), (12, "203.0.113.9"))
            get.assert_called_once()
        saved = json.loads(self.cache.read_text(encoding="utf-8"))
        self.assertEqual(saved["score"], 12)
        self.assertEqual(saved["ip"], "203.0.113.9")
        self.assertFalse(list(self.cache.parent.glob(".ip-health-*")))

    def test_valid_cache_avoids_external_request(self):
        self.cache.parent.mkdir(parents=True)
        self.cache.write_text(json.dumps({
            "ts": time.time(), "score": 7, "ip": "203.0.113.10"
        }), encoding="utf-8")
        with patch.object(network.requests, "get") as get:
            self.assertEqual(network.check_ip_reputation("test-key"), (7, "203.0.113.10"))
            get.assert_not_called()

    def test_out_of_range_cache_score_is_ignored(self):
        self.cache.parent.mkdir(parents=True)
        self.cache.write_text(json.dumps({
            "ts": time.time(), "score": 900, "ip": "203.0.113.12"
        }), encoding="utf-8")
        with patch.object(network.requests, "get") as get:
            self.assertEqual(network.check_ip_reputation(None), (0, "Unknown"))
            get.assert_not_called()
        self.assertIsNone(network._load_ip_cache())

    def test_missing_key_returns_unknown_without_network(self):
        with patch.object(network.requests, "get") as get:
            self.assertEqual(network.check_ip_reputation(None), (0, "Unknown"))
            get.assert_not_called()

    def test_invalid_api_payload_returns_error_without_poisoning_cache(self):
        response = Mock()
        response.json.return_value = {"data": {"ipAddress": "203.0.113.11"}}
        response.raise_for_status.return_value = None
        with patch.object(network.requests, "get", return_value=response):
            self.assertEqual(network.check_ip_reputation("test-key"), (-1, "Error"))
        self.assertFalse(self.cache.exists())

    def test_merchant_parser_reports_missing_declaration_clearly(self):
        with self.assertRaisesRegex(ValueError, "MERCHANTID"):
            network.parse_merchant_info("<html>no merchant metadata</html>")

    def test_post_json_rejects_non_object_payload(self):
        response = Mock()
        response.json.return_value = ["not", "an", "object"]
        response.raise_for_status.return_value = None
        session = Mock()
        session.post.return_value = response
        with self.assertRaisesRegex(ValueError, "JSON object"):
            network.post_json(session, "https://example.test/api", {})


if __name__ == "__main__":
    unittest.main()
