import asyncio
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

import server


class DashboardSecurityTests(unittest.TestCase):
    def test_authentication_fails_closed_without_password(self):
        with patch.object(server.config, "UI_PASS", None):
            with self.assertRaises(HTTPException) as raised:
                server.verify_auth(None)
        self.assertEqual(raised.exception.status_code, 503)

    def test_missing_credentials_are_rejected(self):
        with patch.object(server.config, "UI_USER", "admin"), patch.object(server.config, "UI_PASS", "correct"):
            with self.assertRaises(HTTPException) as raised:
                server.verify_auth(None)
        self.assertEqual(raised.exception.status_code, 401)

    def test_incorrect_credentials_are_rejected(self):
        credentials = HTTPBasicCredentials(username="admin", password="wrong")
        with patch.object(server.config, "UI_USER", "admin"), patch.object(server.config, "UI_PASS", "correct"):
            with self.assertRaises(HTTPException) as raised:
                server.verify_auth(credentials)
        self.assertEqual(raised.exception.status_code, 401)

    def test_correct_credentials_are_accepted(self):
        credentials = HTTPBasicCredentials(username="admin", password="correct")
        with patch.object(server.config, "UI_USER", "admin"), patch.object(server.config, "UI_PASS", "correct"):
            self.assertTrue(server.verify_auth(credentials))

    def test_websocket_ticket_is_single_use(self):
        ticket = server.issue_ws_ticket()
        self.assertTrue(server.consume_ws_ticket(ticket))
        self.assertFalse(server.consume_ws_ticket(ticket))

    def test_config_response_never_includes_account_or_secret_fields(self):
        values = {
            "SETTINGS": {"min_delay": "1", "max_delay": "3", "ui_pass": "secret"},
            "U1": {"u": "account", "p": "secret"},
        }
        with patch.object(server.config, "load_config_dict", return_value=values):
            result = asyncio.run(server.get_config())
        self.assertEqual(result, {"SETTINGS": {"min_delay": "1", "max_delay": "3"}})

    def test_config_update_rejects_sensitive_or_unknown_settings(self):
        data = server.ConfigData(SETTINGS={"ui_pass": "new-secret"})
        with patch.object(server.config, "save_config_dict") as save:
            with self.assertRaises(HTTPException) as raised:
                import asyncio
                asyncio.run(server.post_config(data, auth=True))
        self.assertEqual(raised.exception.status_code, 422)
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
