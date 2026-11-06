import configparser
import os
import tempfile
import unittest
from pathlib import Path

import config


class ConfigPersistenceTests(unittest.TestCase):
    def test_dashboard_settings_are_written_to_ignored_local_config(self):
        original_parser = config.config_parser
        original_cwd = Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as directory:
                os.chdir(directory)
                parser = configparser.ConfigParser()
                parser["SETTINGS"] = {"min_delay": "1.0", "max_delay": "3.0"}
                parser["U1"] = {"u": "template-user", "p": "template-password"}
                config.config_parser = parser

                config.save_config_dict({"SETTINGS": {"min_delay": 2.5, "max_delay": 4.0}})

                local_path = Path("in/config/config.local.ini")
                tracked_path = Path("in/config/config.ini")
                self.assertTrue(local_path.exists())
                self.assertFalse(tracked_path.exists())

                saved = configparser.ConfigParser()
                saved.read(local_path)
                self.assertEqual(saved.getfloat("SETTINGS", "min_delay"), 2.5)
                self.assertEqual(saved.getfloat("SETTINGS", "max_delay"), 4.0)
                self.assertFalse(saved.has_section("U1"))
                self.assertEqual(config.config_parser.getfloat("SETTINGS", "min_delay"), 2.5)
        finally:
            config.config_parser = original_parser
            os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
