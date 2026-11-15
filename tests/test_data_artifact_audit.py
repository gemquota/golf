import csv
import tempfile
import unittest
from pathlib import Path

from data_artifact_audit import audit


class DataArtifactAuditTests(unittest.TestCase):
    def test_reports_exact_duplicates_and_intermediate_fragments_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "one.csv").write_text("a,b\n1,2\n")
            (root / "copy.csv").write_text("a,b\n1,2\n")
            (root / "tmp_0.csv").write_text("a,b\n3,4\n")
            result = audit(root)
            self.assertEqual(result["file_count"], 3)
            self.assertEqual(len(result["exact_duplicates"]), 1)
            self.assertEqual(
                next(item for item in result["files"] if item["path"].endswith("tmp_0.csv"))["role"],
                "ephemeral_worker_fragment",
            )
            self.assertTrue((root / "one.csv").exists())
            self.assertTrue((root / "copy.csv").exists())


if __name__ == "__main__":
    unittest.main()
