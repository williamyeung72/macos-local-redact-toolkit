"""Apple model worker port. Tests inject FakeAppleWorker; production will use Swift later."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@dataclass
class WorkerResult:
    text: str
    entity_map: dict[str, str]


class AppleWorker(Protocol):
    def redact_chunk(self, text: str, entity_map: dict[str, str]) -> WorkerResult:
        """Redact one chunk. entity_map is original value -> placeholder."""
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
