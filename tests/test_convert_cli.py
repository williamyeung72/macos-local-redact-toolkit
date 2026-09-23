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


class ConvertOfficeTests(unittest.TestCase):
    def _pptx(self, folder: Path, with_media: bool) -> Path:
        import zipfile

        src = folder / "deck.pptx"
        with zipfile.ZipFile(src, "w") as z:
            z.writestr("[Content_Types].xml", "<Types></Types>")
            z.writestr("ppt/slides/slide1.xml", "<s></s>")
            if with_media:
                z.writestr("ppt/media/chart.png", PNG)
        return src

    def test_office_without_apple_still_writes_markdown(self) -> None:
        from unittest import mock

        from markitdown_qa import convert_one

        class DeadVision(FakeAppleWorker):
            def vision_markdown(self, image_path: Path) -> str:
                raise RuntimeError("Apple Intelligence is unavailable")

        fake_md = mock.Mock()
        fake_md.convert.return_value = mock.Mock(
            text_content="Slide title", markdown=None, text=None
        )
        with tempfile.TemporaryDirectory() as raw:
            src = self._pptx(Path(raw), with_media=True)
            original = src.read_bytes()
            with mock.patch("markitdown_qa.markitdown_fast", return_value=fake_md):
                out = convert_one(src, worker=DeadVision())
            self.assertTrue(out.is_file())
            self.assertIn("Slide title", out.read_text(encoding="utf-8"))
            self.assertNotIn("CHART_MD", out.read_text(encoding="utf-8"))
            self.assertEqual(src.read_bytes(), original)

    def test_office_with_apple_reads_embedded_images(self) -> None:
        from unittest import mock

        from markitdown_qa import convert_one

        class VisionWorker(FakeAppleWorker):
            def vision_markdown(self, image_path: Path) -> str:
                return "CHART_MD"

        fake_md = mock.Mock()
        fake_md.convert.return_value = mock.Mock(
            text_content="Slide title", markdown=None, text=None
        )
        with tempfile.TemporaryDirectory() as raw:
            src = self._pptx(Path(raw), with_media=True)
            with mock.patch("markitdown_qa.markitdown_fast", return_value=fake_md):
                out = convert_one(src, worker=VisionWorker())
            body = out.read_text(encoding="utf-8")
            self.assertIn("Slide title", body)
            self.assertIn("CHART_MD", body)

    def test_office_empty_text_without_apple_still_writes_markdown(self) -> None:
        from unittest import mock

        from markitdown_qa import convert_one

        class DeadVision(FakeAppleWorker):
            def vision_markdown(self, image_path: Path) -> str:
                raise RuntimeError("Apple Intelligence is unavailable")

        fake_md = mock.Mock()
        fake_md.convert.return_value = mock.Mock(
            text_content="", markdown=None, text=None
        )
        with tempfile.TemporaryDirectory() as raw:
            src = self._pptx(Path(raw), with_media=True)
            with mock.patch("markitdown_qa.markitdown_fast", return_value=fake_md):
                out = convert_one(src, worker=DeadVision())
            self.assertTrue(out.is_file())
            self.assertIn("No extractable text", out.read_text(encoding="utf-8"))

    def test_office_path_has_no_openai_ollama_client(self) -> None:
        source = (ROOT / "scripts" / "markitdown_qa.py").read_text(encoding="utf-8")
        self.assertNotIn("from openai import OpenAI", source)
        self.assertNotIn('api_key="ollama"', source)
        self.assertNotIn("def markitdown_ocr", source)


if __name__ == "__main__":
    unittest.main()
