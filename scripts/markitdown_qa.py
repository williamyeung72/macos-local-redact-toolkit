#!/usr/bin/env python3
"""Convert to Markdown — Microsoft MarkItDown + PyMuPDF for PDF.

Images: EXIF + Apple visual understanding; Tesseract fallback.
PDF: pymupdf4llm by default; MARKITDOWN_PDF_MODE=vision for full-page Apple visual;
text|auto for plain PyMuPDF / heuristic.
Office (docx/pptx/xlsx): fast MarkItDown; embedded images via Apple visual when available.

Other formats: MarkItDown.
"""
from __future__ import annotations

import os
import sys
import tempfile
import zipfile
from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".heic", ".tif", ".tiff"}
OFFICE_EXTS = {".docx", ".pptx", ".xlsx"}
PDF_EXTS = {".pdf"}
# Average extractable chars/page below this → PDF vision path (scanned / image-heavy).
PDF_TEXT_CHARS_PER_PAGE = int(os.environ.get("MARKITDOWN_PDF_CHARS_PER_PAGE", "200"))
# auto | text | vision
PDF_MODE = (os.environ.get("MARKITDOWN_PDF_MODE") or "pymupdf4llm").strip().lower()
PDF_VISION_DPI = int(os.environ.get("MARKITDOWN_PDF_VISION_DPI", "180"))

from apple_worker import AppleWorker, SwiftAppleWorker


def markitdown_fast():
    from markitdown import MarkItDown

    return MarkItDown()


def result_text(result) -> str:
    for attr in ("text_content", "markdown", "text"):
        v = getattr(result, attr, None)
        if v:
            return str(v).strip()
    return ""


def ocr_fallback(path: Path) -> str:
    from PIL import Image
    import pytesseract

    with Image.open(path) as im:
        return pytesseract.image_to_string(im.convert("RGB")).strip()


def convert_image(path: Path, worker: AppleWorker | None = None) -> str:
    meta = ""
    try:
        meta = result_text(markitdown_fast().convert(str(path)))
    except Exception as e:
        print(f"EXIF/meta skipped: {e}", file=sys.stderr)

    active = worker or SwiftAppleWorker()
    try:
        desc = active.vision_markdown(path)
        parts = []
        if meta:
            parts.append(meta.rstrip())
        parts.append("# Description:\n" + desc)
        return "\n\n".join(parts).strip()
    except Exception as e:
        print(f"Apple visual failed ({e}); Tesseract OCR fallback", file=sys.stderr)
        ocr = ocr_fallback(path)
        parts = [p for p in (meta, ("# OCR\n" + ocr) if ocr else "") if p]
        text = "\n\n".join(parts).strip()
        if not text:
            raise RuntimeError(f"image conversion failed: {path.name}") from e
        return text


def pdf_text_stats(path: Path) -> tuple[int, int]:
    """Return (page_count, total_extractable_chars) via PyMuPDF."""
    try:
        import pymupdf

        doc = pymupdf.open(str(path))
        try:
            total = 0
            for page in doc:
                total += len((page.get_text("text") or "").strip())
            return doc.page_count, total
        finally:
            doc.close()
    except Exception as e:
        print(f"PDF text probe failed ({e})", file=sys.stderr)
        return 0, 0


def pdf_is_hard_scan(path: Path) -> bool:
    pages, chars = pdf_text_stats(path)
    if pages <= 0:
        print(f"PDF probe=unreadable file={path.name} → vision candidate", file=sys.stderr)
        return True
    avg = chars / pages
    hard = avg < PDF_TEXT_CHARS_PER_PAGE
    print(
        f"PDF probe pages={pages} chars={chars} avg={avg:.1f} "
        f"threshold={PDF_TEXT_CHARS_PER_PAGE} hard_scan={hard} file={path.name}",
        file=sys.stderr,
    )
    return hard


def convert_pdf_pymupdf4llm(path: Path) -> str:
    import pymupdf4llm

    md = pymupdf4llm.to_markdown(str(path))
    text = (md or "").strip()
    if not text:
        raise RuntimeError("pymupdf4llm returned empty markdown")
    print(f"PDF path=pymupdf4llm file={path.name}", file=sys.stderr)
    return text


def convert_pdf_pymupdf(path: Path) -> str:
    import pymupdf

    doc = pymupdf.open(str(path))
    try:
        parts: list[str] = []
        for i, page in enumerate(doc):
            # Sort blocks by visual reading order (top→bottom, left→right).
            blocks = page.get_text("blocks") or []
            text_blocks = []
            for b in blocks:
                if len(b) < 5 or not isinstance(b[4], str):
                    continue
                s = b[4].strip()
                if s:
                    text_blocks.append((float(b[1]), float(b[0]), s))
            text_blocks.sort(key=lambda x: (round(x[0], 1), round(x[1], 1)))
            chunk = "\n".join(tb[2] for tb in text_blocks).strip()
            if not chunk:
                chunk = (page.get_text("text") or "").strip()
            if not chunk:
                continue
            if doc.page_count > 1:
                parts.append(f"## Page {i + 1}\n\n{chunk}")
            else:
                parts.append(chunk)
        text = "\n\n".join(parts).strip()
        if not text:
            raise RuntimeError("PyMuPDF extracted empty text")
        print(f"PDF path=pymupdf pages={doc.page_count} file={path.name}", file=sys.stderr)
        return text
    finally:
        doc.close()


def convert_pdf_vision(path: Path, worker: AppleWorker | None = None) -> str:
    import pymupdf

    active = worker or SwiftAppleWorker()
    doc = pymupdf.open(str(path))
    try:
        parts: list[str] = []
        zoom = PDF_VISION_DPI / 72.0
        mat = pymupdf.Matrix(zoom, zoom)
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=mat, alpha=False)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                pix.save(str(tmp_path))
                print(
                    f"PDF vision page={i + 1}/{doc.page_count} "
                    f"dpi={PDF_VISION_DPI} file={path.name}",
                    file=sys.stderr,
                )
                try:
                    page_md = active.vision_markdown(tmp_path)
                except Exception as e:
                    print(f"Apple visual failed ({e}); Tesseract OCR fallback", file=sys.stderr)
                    page_md = ocr_fallback(tmp_path)

            finally:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass
            if doc.page_count > 1:
                parts.append(f"## Page {i + 1}\n\n{page_md}")
            else:
                parts.append(page_md)
        text = "\n\n".join(parts).strip()
        if not text:
            raise RuntimeError("PDF vision returned empty markdown")
        print(f"PDF path=vision pages={doc.page_count} file={path.name}", file=sys.stderr)
        return text
    finally:
        doc.close()


def convert_pdf(path: Path, worker: AppleWorker | None = None) -> str:
    mode = PDF_MODE
    aliases = {
        "md": "pymupdf4llm",
        "llm": "pymupdf4llm",
        "4llm": "pymupdf4llm",
        "default": "pymupdf4llm",
    }
    mode = aliases.get(mode, mode)
    if mode not in {"pymupdf4llm", "auto", "text", "vision"}:
        print(f"Unknown MARKITDOWN_PDF_MODE={mode!r}; using pymupdf4llm", file=sys.stderr)
        mode = "pymupdf4llm"

    if mode == "vision":
        try:
            return convert_pdf_vision(path, worker=worker)
        except Exception as e:
            print(f"PDF vision failed ({e}); falling back to pymupdf4llm", file=sys.stderr)
            try:
                return convert_pdf_pymupdf4llm(path)
            except Exception as e2:
                print(f"pymupdf4llm failed ({e2}); plain PyMuPDF", file=sys.stderr)
                return convert_pdf_pymupdf(path)

    if mode == "text":
        return convert_pdf_pymupdf(path)

    if mode == "auto":
        if pdf_is_hard_scan(path):
            try:
                return convert_pdf_vision(path, worker=worker)
            except Exception as e:
                print(f"PDF vision failed ({e}); falling back to pymupdf4llm", file=sys.stderr)
        # text-heavy or vision failed → pymupdf4llm
        try:
            return convert_pdf_pymupdf4llm(path)
        except Exception as e:
            print(f"pymupdf4llm failed ({e}); plain PyMuPDF", file=sys.stderr)
            return convert_pdf_pymupdf(path)

    # default: pymupdf4llm
    try:
        return convert_pdf_pymupdf4llm(path)
    except Exception as e:
        print(f"pymupdf4llm failed ({e}); plain PyMuPDF then MarkItDown", file=sys.stderr)
        try:
            return convert_pdf_pymupdf(path)
        except Exception as e2:
            print(f"PyMuPDF text failed ({e2}); MarkItDown fast", file=sys.stderr)
            return result_text(markitdown_fast().convert(str(path)))



def _is_office_media_image(member: str) -> bool:
    lower = member.replace("\\", "/").lower()
    if "/media/" not in lower:
        return False
    return Path(lower).suffix in IMAGE_EXTS


def convert_office(path: Path, worker: AppleWorker | None = None) -> str:
    print(f"Office path=markitdown file={path.name}", file=sys.stderr)
    text = result_text(markitdown_fast().convert(str(path)))
    active = worker if worker is not None else SwiftAppleWorker()
    image_markdown: list[str] = []
    try:
        with zipfile.ZipFile(path) as zf:
            members = [n for n in zf.namelist() if _is_office_media_image(n)]
            for name in members:
                suffix = Path(name).suffix.lower() or ".png"
                tmp_path: Path | None = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                        tmp.write(zf.read(name))
                        tmp_path = Path(tmp.name)
                    desc = (active.vision_markdown(tmp_path) or "").strip()
                    if desc:
                        image_markdown.append(desc)
                except Exception as e:
                    print(
                        f"Office embedded image skipped ({name}): {e}",
                        file=sys.stderr,
                    )
                finally:
                    if tmp_path is not None:
                        tmp_path.unlink(missing_ok=True)
    except zipfile.BadZipFile:
        print(f"Office zip skipped (not a zip): {path.name}", file=sys.stderr)
    parts = [p for p in (text, *image_markdown) if p]
    if parts:
        return "\n\n".join(parts).strip()
    return f"(No extractable text from {path.name})"


def convert_one(path: Path, worker: AppleWorker | None = None) -> Path:
    out = path.with_suffix(".md")
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        text = convert_image(path, worker=worker)
    elif ext in PDF_EXTS:
        text = convert_pdf(path, worker=worker)
    elif ext in OFFICE_EXTS:
        text = convert_office(path, worker=worker)
    else:
        text = result_text(markitdown_fast().convert(str(path)))
    if not text.strip():
        raise RuntimeError(f"empty markdown: {path.name}")
    out.write_text(text.strip() + "\n", encoding="utf-8")
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: markitdown_qa.py <files...>", file=sys.stderr)
        print(
            "env: MARKITDOWN_PDF_MODE=pymupdf4llm|auto|text|vision  "
            "MARKITDOWN_PDF_CHARS_PER_PAGE  MARKITDOWN_PDF_VISION_DPI",
            file=sys.stderr,
        )
        return 1
    ok = fail = 0
    for raw in argv[1:]:
        p = Path(raw).expanduser().resolve()
        try:
            if not p.is_file():
                raise FileNotFoundError(str(p))
            out = convert_one(p)
            print(f"ok: {p} -> {out}")
            ok += 1
        except Exception as e:
            fail += 1
            print(f"ERROR {p}: {e}", file=sys.stderr)
    if ok and not fail:
        return 0
    if ok and fail:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
