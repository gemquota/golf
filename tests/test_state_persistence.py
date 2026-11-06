import json
import tempfile
import unittest
from pathlib import Path

from state_persistence import atomic_write_json


class AtomicJsonPersistenceTests(unittest.TestCase):
    def test_replaces_existing_json_with_complete_document(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "state.json"
            target.write_text('{"old": true}\n', encoding="utf-8")
            atomic_write_json(target, {"new": [1, 2, 3]})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"new": [1, 2, 3]})
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), ["state.json"])

    def test_creates_missing_parent_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "nested" / "state.json"
            atomic_write_json(target, {"ok": True})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"ok": True})


if __name__ == "__main__":
    unittest.main()
