#!/usr/bin/env python3
"""Ollama AI Redact.

Prefer Markdown when possible:
1) Convert to a sibling .md via markitdown_qa.py (no Ollama for convert)
2) Redact that .md with a text model -> *_redacted.md
Only if conversion fails, is empty, or is image metadata-only: vision model.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

import ollama

from apple_worker import AppleWorker, FakeAppleWorker, SwiftAppleWorker, WorkerResult

TEXT_MODEL = os.environ.get("OLLAMA_REDACT_TEXT_MODEL", "llama3.1:latest")
VISION_MODEL = os.environ.get("OLLAMA_REDACT_VISION_MODEL", "qwen3.5:4b")
LOG_PATH = Path.home() / "Library" / "Logs" / "ollama-redact.log"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".heic", ".tif", ".tiff"}
EXIF_ONLY_KEYS = {
    "ImageSize", "Title", "Caption", "Description", "Keywords", "Artist",
    "Author", "DateTimeOriginal", "CreateDate", "GPSPosition",
}

SYSTEM_PROMPT = """You are a data redaction assistant. Find sensitive information and replace it with typed, stable placeholders.

Rules:
- Reuse the same token for the same entity, e.g. the first email is always [EMAIL_1]; a different email is [EMAIL_2]
- Replace personal names (Chinese and English): [PERSON_n]
- Phone [PHONE_n], email [EMAIL_n], address [ADDRESS_n]
- ID / passport [ID_NUMBER_n], credit-card / bank account [ACCOUNT_n]
- API key / JWT / token / password / secret [SECRET_n]
- Order / Payment / Host / IP [ORDER_ID_n] / [PAYMENT_ID_n] / [HOST_n] / [IP_n]
- Keep the original layout (Markdown headings, lists, tables)
- Output only the redacted document; no preamble or explanation
"""


def log(msg: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except Exception:
        pass


def notify(title: str, body: str) -> None:
    safe_title = title.replace('"', '\\"')
    safe_body = body.replace('"', '\\"')
    os.system(
        f'/usr/bin/osascript -e \'display notification "{safe_body}" with title "{safe_title}"\''
    )


def chat_text(content: str) -> str:
    max_chars = int(os.environ.get("OLLAMA_REDACT_MAX_CHARS", "60000"))
    if len(content) > max_chars:
        content = content[:max_chars] + "\n\n[TRUNCATED_FOR_REDACTION]"
    resp = ollama.chat(
        model=TEXT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
    )
    return resp["message"]["content"]


def _default_worker() -> AppleWorker:
    kind = os.environ.get("REDACT_WORKER", "").strip().lower()
    if kind == "fake":
        return FakeAppleWorker()
    if kind == "ollama":
        return OllamaTextWorker()
    return SwiftAppleWorker()


class OllamaTextWorker:
    """Existing Ollama text path, wrapped as an AppleWorker (expand; removed later)."""

    def redact_chunk(self, text: str, entity_map: dict[str, str]) -> WorkerResult:
        return WorkerResult(text=chat_text(text), entity_map=dict(entity_map))


def chat_image(path: Path) -> str:
    resp = ollama.chat(
        model=VISION_MODEL,
        messages=[{
            "role": "user",
            "content": SYSTEM_PROMPT + "\nRead this image, extract the text, and output redacted Markdown:",
            "images": [str(path)],
        }],
    )
    return resp["message"]["content"]


def is_useful_md(text: str, src_ext: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if src_ext.lower() in IMAGE_EXTS:
        lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
        # useless if only EXIF key lines and no OCR section / body
        if lines and all(
            (ln.split(":", 1)[0] in EXIF_ONLY_KEYS) or ln.startswith("#")
            for ln in lines
        ) and "# OCR" not in t and len(t) < 80:
            # allow if has OCR section with content
            pass
        if "# OCR" in t:
            after = t.split("# OCR", 1)[-1].strip()
            if after:
                return True
        # only metadata keys?
        data_lines = [ln for ln in lines if not ln.startswith("#")]
        if data_lines and all(ln.split(":", 1)[0] in EXIF_ONLY_KEYS for ln in data_lines):
            return False
    return True


def to_markdown(path: Path) -> Path:
    """Convert to sibling .md via markitdown_qa in the markitdown pipx Python."""
    if path.suffix.lower() == ".md":
        return path

    import subprocess

    helper = Path.home() / "Scripts" / "markitdown_qa.py"
    mark_py = (
        Path.home()
        / "Library"
        / "Application Support"
        / "pipx"
        / "venvs"
        / "markitdown"
        / "bin"
        / "python"
    )
    if not helper.exists() or not mark_py.exists():
        raise RuntimeError("markitdown_qa / pipx python missing")

    proc = subprocess.run(
        [str(mark_py), str(helper), str(path)],
        capture_output=True,
        text=True,
    )
    out = path.with_suffix(".md")
    if proc.returncode != 0 or not out.exists():
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(err or f"markitdown_qa failed ({proc.returncode})")
    return out

def chunk_text(text: str, max_chars: int) -> list[str]:
    if max_chars <= 0 or len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    buf = ""
    for line in text.splitlines(keepends=True):
        if buf and len(buf) + len(line) > max_chars:
            chunks.append(buf)
            buf = line
        else:
            buf += line
    if buf:
        chunks.append(buf)
    return chunks or [text]


def redact_markdown(content: str, worker: AppleWorker) -> str:
    max_chars = int(os.environ.get("REDACT_CHUNK_CHARS", "60000"))
    entity_map: dict[str, str] = {}
    parts: list[str] = []
    for chunk in chunk_text(content, max_chars):
        result = worker.redact_chunk(chunk, dict(entity_map))
        for original, token in result.entity_map.items():
            if original not in entity_map:
                entity_map[original] = token
        parts.append(result.text)
    return "".join(parts)


def redact_file(file_path: str, worker: AppleWorker | None = None) -> Path | None:
    path = Path(file_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        log(f"skip missing: {file_path}")
        return None

    active = worker or _default_worker()
    ext = path.suffix.lower()
    out = path.with_name(f"{path.stem}_redacted.md")

    # Already markdown: redact directly
    if ext == ".md":
        content = path.read_text(encoding="utf-8", errors="ignore")
        if not content.strip():
            raise RuntimeError(f"empty md: {path.name}")
        out.write_text(redact_markdown(content, active), encoding="utf-8")
        log(f"ok(md): {path} -> {out}")
        return out

    # Try MarkItDown -> md first (preferred)
    md_path = None
    md_text = ""
    try:
        md_path = to_markdown(path)
        md_text = md_path.read_text(encoding="utf-8", errors="ignore")
        log(f"md: {path} -> {md_path}")
    except Exception as e:
        log(f"md convert failed: {path}: {e}")

    if md_path and is_useful_md(md_text, ext):
        # Redact from markdown; output *_redacted.md next to source stem
        # If source was foo.pdf -> foo.md -> foo_redacted.md
        out = md_path.with_name(f"{md_path.stem}_redacted.md")
        out.write_text(redact_markdown(md_text, active), encoding="utf-8")
        log(f"ok(md-redact): {path} -> {md_path} -> {out}")
        return out

    # Fallback: vision only when md path failed / not useful
    if ext in IMAGE_EXTS:
        out = path.with_name(f"{path.stem}_redacted.md")
        out.write_text(chat_image(path), encoding="utf-8")
        log(f"ok(vision-fallback): {path} -> {out}")
        return out

    raise RuntimeError(
        f"could not produce useful Markdown, and file is not an image for vision fallback: {path.name}"
    )


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        notify("Ollama AI Redact", "No file received")
        return 1

    ok = fail = 0
    worker = _default_worker()
    last_err = ""
    for raw in argv[1:]:
        try:
            if redact_file(raw, worker=worker):
                ok += 1
            else:
                fail += 1
        except Exception as e:
            fail += 1
            last_err = str(e)
            log(f"ERROR {raw}: {e}\n{traceback.format_exc()}")

    if ok and not fail:
        notify("Ollama AI Redact", f"Wrote {ok} *_redacted.md file(s)")
        return 0
    if ok and fail:
        notify("Ollama AI Redact", f"Succeeded {ok}, failed {fail} (see Logs)")
        return 2
    body = last_err.strip() or "See ~/Library/Logs/ollama-redact.log"
    notify("Ollama AI Redact failed", body[:180])
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
