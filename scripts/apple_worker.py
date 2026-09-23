"""Apple model worker port. Tests inject FakeAppleWorker; production uses a Swift helper."""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import base64

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

REDACT_INSTRUCTIONS = """Extract every sensitive span from the document chunk.

Assign typed placeholders:
- People names (Chinese or English): [PERSON_n]
- Phone numbers: [PHONE_n]
- Email addresses: [EMAIL_n]
- Street / mailing addresses: [ADDRESS_n]
- ID / passport numbers: [ID_NUMBER_n]
- Bank / card account numbers: [ACCOUNT_n]
- API keys, JWT, passwords, secrets: [SECRET_n]
- Order IDs, payment IDs, hostnames, IP addresses: [ORDER_ID_n], [PAYMENT_ID_n], [HOST_n], [IP_n]

Reuse existing entity_map placeholders for the same original string.
Do not invent spans that are not present. Do not rewrite the document.
"""


@dataclass
class WorkerResult:
    text: str
    entity_map: dict[str, str]


class AppleWorker(Protocol):
    def redact_chunk(self, text: str, entity_map: dict[str, str]) -> WorkerResult:
        """Redact one chunk. entity_map is original value -> placeholder."""
        ...

    def vision_markdown(self, image_path: Path) -> str:
        """Turn an image into Markdown."""
        ...


class FakeAppleWorker:
    """Deterministic stand-in: emails become typed placeholders via the Entity map."""

    def redact_chunk(self, text: str, entity_map: dict[str, str]) -> WorkerResult:
        mapping = dict(entity_map)

        def repl(match: re.Match[str]) -> str:
            email = match.group(0)
            if email not in mapping:
                n = sum(1 for token in mapping.values() if token.startswith("[EMAIL_")) + 1
                mapping[email] = f"[EMAIL_{n}]"
            return mapping[email]

        return WorkerResult(text=EMAIL_RE.sub(repl, text), entity_map=mapping)

    def vision_markdown(self, image_path: Path) -> str:
        return f"FAKE_VISION {image_path.name}"


def default_helper_path() -> Path:
    env = os.environ.get("APPLE_REDACT_HELPER", "").strip()
    if env:
        return Path(env).expanduser()
    installed = Path.home() / "Scripts" / "apple-redact-worker"
    if installed.is_file():
        return installed
    bundled = (
        Path(__file__).resolve().parents[1]
        / "native"
        / "apple-redact-worker"
        / "bin"
        / "apple-redact-worker"
    )
    if bundled.is_file():
        return bundled
    return installed


class SwiftAppleWorker:
    """Launch the Swift helper once per chunk. JSON on stdin/stdout; argv is only the helper path."""

    def __init__(self, helper: Path | None = None) -> None:
        self.helper = Path(helper) if helper is not None else default_helper_path()
        self.last_argv: list[str] = []

    def redact_chunk(self, text: str, entity_map: dict[str, str]) -> WorkerResult:
        data = self._invoke(
            {
                "op": "redact_chunk",
                "text": text,
                "entity_map": entity_map,
                "instructions": REDACT_INSTRUCTIONS,
            }
        )
        out_text = data.get("text")
        out_map = data.get("entity_map")
        if not isinstance(out_text, str) or not isinstance(out_map, dict):
            raise RuntimeError("Apple Intelligence worker returned an incomplete result")
        return WorkerResult(
            text=out_text,
            entity_map={str(k): str(v) for k, v in out_map.items()},
        )

    def vision_markdown(self, image_path: Path) -> str:
        import mimetypes

        mime, _ = mimetypes.guess_type(str(image_path))
        if not mime:
            mime = "image/jpeg"
        data = self._invoke(
            {
                "op": "vision_markdown",
                "image_b64": base64.b64encode(image_path.read_bytes()).decode("ascii"),
                "mime": mime,
                "instructions": (
                    "Extract ALL visible text from this image into clean Markdown. "
                    "Preserve headings, lists, and tables when recognizable. "
                    "Prefer Traditional Chinese when the source is Chinese. "
                    "Output Markdown only."
                ),
            }
        )
        out_text = data.get("text")
        if not isinstance(out_text, str) or not out_text.strip():
            raise RuntimeError("Apple visual understanding returned empty markdown")
        return out_text.strip()

    def _invoke(self, payload: dict) -> dict:
        if not self.helper.is_file() or not os.access(self.helper, os.X_OK):
            raise RuntimeError(
                "Apple Intelligence worker not found. "
                "Install the helper and enable Apple Intelligence on macOS 26+."
            )
        argv = [str(self.helper)]
        self.last_argv = argv
        proc = subprocess.run(
            argv,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(
                err or "Apple Intelligence worker failed. Enable Apple Intelligence on macOS 26+."
            )
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError("Apple Intelligence worker returned invalid JSON") from e
        if not data.get("ok"):
            raise RuntimeError(
                str(data.get("error") or "Apple Intelligence is unavailable")
            )
        return data
