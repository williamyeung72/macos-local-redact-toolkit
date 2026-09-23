"""Redaction CLI seam: sibling draft, stable placeholders, no entity-map sidecar."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from apple_worker import FakeAppleWorker, SwiftAppleWorker  # noqa: E402
from ollama_redact import main, redact_file  # noqa: E402


class RedactMarkdownTests(unittest.TestCase):
    def test_writes_redacted_sibling_and_leaves_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            src = folder / "note.md"
            src.write_text("Contact: alex.chan@example.test\n", encoding="utf-8")
            out = redact_file(str(src), worker=FakeAppleWorker())
            self.assertIsNotNone(out)
            assert out is not None
            self.assertEqual(out.name, "note_redacted.md")
            self.assertTrue(out.is_file())
            self.assertEqual(
                src.read_text(encoding="utf-8"),
                "Contact: alex.chan@example.test\n",
            )
            self.assertIn("[EMAIL_1]", out.read_text(encoding="utf-8"))
            self.assertNotIn("alex.chan@example.test", out.read_text(encoding="utf-8"))

    def test_same_email_keeps_placeholder_across_chunks(self) -> None:
        class CountingWorker:
            def __init__(self) -> None:
                self.inner = FakeAppleWorker()
                self.calls = 0

            def redact_chunk(self, text: str, entity_map: dict[str, str]):
                self.calls += 1
                return self.inner.redact_chunk(text, entity_map)

        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            src = folder / "long.md"
            src.write_text(
                "First mention alex.chan@example.test\n"
                + ("padding line\n" * 30)
                + "Other jamie.chan@example.test and again alex.chan@example.test\n",
                encoding="utf-8",
            )
            worker = CountingWorker()
            with mock.patch.dict("os.environ", {"REDACT_CHUNK_CHARS": "50"}):
                out = redact_file(str(src), worker=worker)
            assert out is not None
            self.assertGreaterEqual(worker.calls, 2)
            body = out.read_text(encoding="utf-8")
            self.assertEqual(body.count("[EMAIL_1]"), 2)
            self.assertEqual(body.count("[EMAIL_2]"), 1)
            self.assertNotIn("alex.chan@example.test", body)
            self.assertNotIn("jamie.chan@example.test", body)
            sidecars = [p for p in folder.iterdir() if p.suffix != ".md" or "map" in p.name.lower()]
            self.assertEqual([p.name for p in folder.iterdir() if "map" in p.name.lower()], [])

    def test_cli_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            ok_src = folder / "ok.md"
            ok_src.write_text("Hi alex.chan@example.test\n", encoding="utf-8")
            with mock.patch("ollama_redact.notify"):
                with mock.patch.dict("os.environ", {"REDACT_WORKER": "fake"}):
                    self.assertEqual(
                        main(["ollama_redact.py", str(ok_src)]),
                        0,
                    )
                    self.assertEqual(
                        main(["ollama_redact.py", str(ok_src), str(folder / "missing.md")]),
                        2,
                    )
                    self.assertEqual(main(["ollama_redact.py"]), 1)
                    self.assertEqual(
                        main(["ollama_redact.py", str(folder / "gone-a.md"), str(folder / "gone-b.md")]),
                        1,
                    )

    def test_convert_default_pdf_mode_does_not_use_apple_worker(self) -> None:
        source = (ROOT / "scripts" / "markitdown_qa.py").read_text(encoding="utf-8")
        self.assertIn('PDF_MODE = (os.environ.get("MARKITDOWN_PDF_MODE") or "pymupdf4llm")', source)
        self.assertIn('print(f"PDF path=pymupdf4llm file={path.name}"', source)


class SwiftWorkerTests(unittest.TestCase):
    def test_missing_helper_does_not_write_partial_draft(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            src = folder / "note.md"
            src.write_text("Contact: alex.chan@example.test\n", encoding="utf-8")
            worker = SwiftAppleWorker(helper=folder / "no-such-worker")
            with self.assertRaises(RuntimeError) as ctx:
                redact_file(str(src), worker=worker)
            self.assertIn("Apple", str(ctx.exception))
            self.assertFalse((folder / "note_redacted.md").exists())
            self.assertEqual(
                src.read_text(encoding="utf-8"),
                "Contact: alex.chan@example.test\n",
            )

    def test_helper_gets_chunk_on_stdin_not_argv(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            stub = folder / "stub-worker"
            stub.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "req = json.load(sys.stdin)\n"
                "assert req.get('op') == 'redact_chunk'\n"
                "text = req['text']\n"
                "emap = dict(req.get('entity_map') or {})\n"
                "key = 'alex.chan@example.test'\n"
                "if key in text:\n"
                "    token = emap.get(key) or '[EMAIL_1]'\n"
                "    emap[key] = token\n"
                "    text = text.replace(key, token)\n"
                "json.dump({'ok': True, 'text': text, 'entity_map': emap}, sys.stdout)\n",
                encoding="utf-8",
            )
            stub.chmod(0o755)
            src = folder / "note.md"
            src.write_text("Contact: alex.chan@example.test\n", encoding="utf-8")
            worker = SwiftAppleWorker(helper=stub)
            out = redact_file(str(src), worker=worker)
            assert out is not None
            self.assertIn("[EMAIL_1]", out.read_text(encoding="utf-8"))
            self.assertEqual(worker.last_argv[0], str(stub))
            joined = " ".join(worker.last_argv)
            self.assertNotIn("alex.chan@example.test", joined)

    def test_unavailable_intelligence_does_not_write_draft(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            stub = folder / "down-worker"
            stub.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "json.dump({'ok': False, 'error': 'Apple Intelligence is unavailable on this Mac'}, sys.stdout)\n"
                "sys.exit(1)\n",
                encoding="utf-8",
            )
            stub.chmod(0o755)
            src = folder / "note.md"
            src.write_text("Contact: alex.chan@example.test\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                redact_file(str(src), worker=SwiftAppleWorker(helper=stub))
            self.assertFalse((folder / "note_redacted.md").exists())


if __name__ == "__main__":
    unittest.main()
