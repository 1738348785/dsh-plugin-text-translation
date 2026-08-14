"""Smoke tests for the bundled python/local_helper.py engine.

Runs the helper as a subprocess (end-to-end CLI contract) and asserts:
- inspect reports the fixture's format / item count / speakers / tag counts;
- extract masks engine tags into placeholders and produces valid batches;
- assemble restores the original file losslessly (src untouched, no leftover
  placeholders, trans == src when the masked text is fed back verbatim).
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HELPER = Path(__file__).resolve().parent.parent / "python" / "local_helper.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_game_dialogue.json"

PLACEHOLDER = "TAG_"


def run_helper(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HELPER), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )


class InspectTest(unittest.TestCase):
    def test_inspect_reports_summary(self) -> None:
        r = run_helper("inspect", str(FIXTURE))
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["format"], "json")
        self.assertEqual(data["total_items"], 3)
        self.assertEqual(len(data["speakers"]), 3)
        self.assertGreaterEqual(len(data["tag_counts"]), 1)
        self.assertEqual(len(data["sample_preview"]), 3)


class ExtractTest(unittest.TestCase):
    def test_extract_masks_tags_and_batches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "extract.json"
            r = run_helper("extract", str(FIXTURE), "--batch-size", "2", "-o", str(out))
            self.assertEqual(r.returncode, 0, msg=r.stderr)
            summary = json.loads(r.stdout.strip())
            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["total_items"], 3)
            self.assertEqual(summary["total_batches"], 2)

            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["total_items"], 3)
            self.assertEqual(data["total_batches"], 2)  # ceil(3 / 2)

            items = [it for b in data["batches"] for it in b["items"]]
            self.assertEqual(len(items), 3)
            for it in items:
                self.assertIn(PLACEHOLDER, it["text"], "masked text must contain placeholders")
                self.assertGreaterEqual(len(it["tag_map"]), 1, "tag_map must map placeholders back")


class AssembleTest(unittest.TestCase):
    def test_assemble_is_lossless(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            extract_out = tmp / "extract.json"
            r = run_helper("extract", str(FIXTURE), "--batch-size", "5", "-o", str(extract_out))
            self.assertEqual(r.returncode, 0, msg=r.stderr)

            data = json.loads(extract_out.read_text(encoding="utf-8"))
            items = [
                {"id": it["id"], "text": it["text"]}
                for b in data["batches"]
                for it in b["items"]
            ]

            trans = tmp / "translations.json"
            trans.write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")

            out = tmp / "output.json"
            r = run_helper("assemble", str(FIXTURE), str(trans), str(out))
            self.assertEqual(r.returncode, 0, msg=r.stderr)
            summary = json.loads(r.stdout)
            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["total_items_assembled"], 3)

            result = json.loads(out.read_text(encoding="utf-8"))
            original = json.loads(FIXTURE.read_text(encoding="utf-8"))
            for msg_id, entry in original.items():
                self.assertIn(msg_id, result)
                self.assertEqual(result[msg_id]["src"], entry["src"], "src must stay untouched")
                self.assertEqual(result[msg_id]["trans"], entry["src"], "trans must equal src when fed verbatim")

            raw = out.read_text(encoding="utf-8")
            self.assertNotIn(PLACEHOLDER, raw, "no placeholder may survive assembly")


if __name__ == "__main__":
    unittest.main(verbosity=2)
