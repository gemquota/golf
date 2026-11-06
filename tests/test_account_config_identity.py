import config
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class AccountConfigIdentityTests(unittest.TestCase):
    def test_missing_first_account_does_not_renumber_later_account(self):
        parser = config.config_parser
        original = config.config_parser
        import configparser
        replacement = configparser.ConfigParser()
        replacement["SETTINGS"] = {}
        replacement["U2"] = {"u": "second-user", "p": "second-pass"}
        with patch.object(config, "config_parser", replacement), \
             patch.object(config, "_env", return_value=None), \
             patch("pathlib.Path.read_text", return_value="https://example.test\n"), \
             patch("db.get_url_scores", return_value={}):
            urls, records = config.parse_account_records()
        self.assertEqual(urls, ["https://example.test"])
        self.assertEqual(records, [("U2", "second-user", "second-pass")])
        config.config_parser = original


if __name__ == "__main__":
    unittest.main()
