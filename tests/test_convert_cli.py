"""Convert to Markdown seam: Apple visual when available, OCR fallback, PDF default local."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from apple_worker import FakeAppleWorker, WorkerResult  # noqa: E402

# 1x1 transparent PNG
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


class ConvertImageTests(unittest.TestCase):
    def test_image_uses_apple_visual_and_leaves_source(self) -> None:
        from markitdown_qa import convert_one

        class VisionWorker(FakeAppleWorker):
            def vision_markdown(self, image_path: Path) -> str:
                return f"FAKE_VISION {image_path.name}"

        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            src = folder / "photo.png"
            src.write_bytes(PNG)
            original = src.read_bytes()
            out = convert_one(src, worker=VisionWorker())
            self.assertEqual(out.name, "photo.md")
            self.assertIn("FAKE_VISION photo.png", out.read_text(encoding="utf-8"))
            self.assertEqual(src.read_bytes(), original)

    def test_heic_still_converts_with_visual_worker(self) -> None:
        from markitdown_qa import convert_one

        class VisionWorker(FakeAppleWorker):
            def vision_markdown(self, image_path: Path) -> str:
                return f"HEIC_OK {image_path.suffix}"

        with tempfile.TemporaryDirectory() as raw:
            src = Path(raw) / "img.heic"
            src.write_bytes(PNG)
            out = convert_one(src, worker=VisionWorker())
            self.assertTrue(out.is_file())
            self.assertIn("HEIC_OK .heic", out.read_text(encoding="utf-8"))

    def test_visual_failure_falls_back_to_ocr(self) -> None:
        from unittest import mock

        from markitdown_qa import convert_one

        class DeadVision(FakeAppleWorker):
            def vision_markdown(self, image_path: Path) -> str:
                raise RuntimeError("Apple Intelligence is unavailable")

        with tempfile.TemporaryDirectory() as raw:
            src = Path(raw) / "scan.png"
            src.write_bytes(PNG)
            with mock.patch("markitdown_qa.ocr_fallback", return_value="OCR_TEXT"):
                out = convert_one(src, worker=DeadVision())
            self.assertTrue(out.is_file())
            self.assertIn("OCR_TEXT", out.read_text(encoding="utf-8"))

    def test_default_pdf_mode_is_pymupdf4llm(self) -> None:
        import markitdown_qa as qa

        self.assertEqual(qa.PDF_MODE, "pymupdf4llm")


if __name__ == "__main__":
    unittest.main()
