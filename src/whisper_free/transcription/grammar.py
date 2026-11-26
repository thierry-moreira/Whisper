"""Grammar / spelling correction with a local LanguageTool server.

Design notes
------------
* The ``language_tool_python`` import is deferred — it is only needed when the
  grammar engine actually starts.
* Only "safe" correction categories are applied automatically (typos, grammar,
  punctuation, casing...). Style suggestions are collected but *not* applied,
  so the dictated text keeps the user's voice.
* If Java / LanguageTool is unavailable the corrector degrades gracefully:
  the text still passes through :func:`cleanup_text` (whitespace, spacing
  before punctuation, sentence capitalisation).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from whisper_free.config.settings import Settings
from whisper_free.transcription.java_runtime import JavaRuntimeManager
from whisper_free.utils.logging import get_logger

logger = get_logger("whisper_free.grammar")

# Categories whose suggestions are safe to auto-apply for dictation.
SAFE_CATEGORIES = frozenset(
    {
        "TYPOS",
        "GRAMMAR",
        "PUNCTUATION",
        "CASING",
        "CONFUSED_WORDS",
        "REDUNDANCY",
        "COMPOUNDS",
        "AGREEMENT",
        "MISC",  # pt-BR specific spelling rules
    }
)

_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?%)])")
_SPACE_AFTER_OPEN_RE = re.compile(r"([(¿¡])\s+")


@dataclass
class GrammarMatch:
    """A single correction suggestion (subset of LanguageTool's Match)."""

    rule_id: str = ""
    message: str = ""
    replacement: str = ""
    offset: int = 0
    length: int = 0
    category: str = ""
    applied: bool = False


@dataclass
class GrammarResult:
    """Outcome of one grammar-correction pass."""

    original: str = ""
    corrected: str = ""
    matches: list[GrammarMatch] = field(default_factory=list)
    elapsed_s: float = 0.0
    engine_used: str = "none"  # "languagetool" | "cleanup" | "none"

    @property
    def changed(self) -> bool:
        return self.original != self.corrected


def cleanup_text(text: str) -> str:
    """Light, always-safe normalisation applied to every transcription."""
    if not text:
        return ""
    cleaned = text.strip()
    cleaned = _MULTI_SPACE_RE.sub(" ", cleaned)
    cleaned = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", cleaned)
    cleaned = _SPACE_AFTER_OPEN_RE.sub(r"\1", cleaned)
    if cleaned and cleaned[0].isalpha():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


def apply_matches(text: str, matches: list[GrammarMatch]) -> str:
    """Apply replacements right-to-left so offsets remain valid."""
    ordered = sorted(
        (m for m in matches if m.replacement),
        key=lambda m: m.offset,
        reverse=True,
    )
    result = text
    for match in ordered:
        start = match.offset
        end = match.offset + match.length
        if start < 0 or end > len(result) or start >= end:
            continue
        result = result[:start] + match.replacement + result[end:]
        match.applied = True
    return result


class GrammarCorrector:
    """Wraps a local LanguageTool server with graceful degradation."""

    def __init__(self, settings: Settings, java_manager: JavaRuntimeManager | None = None) -> None:
        self._settings = settings
        self._java = java_manager or JavaRuntimeManager()
        self._tool: Any | None = None
        self._engine = "none"
        self._start_attempted = False

    # ------------------------------------------------------------------ API
    @property
    def engine(self) -> str:
        return self._engine

    @property
    def is_ready(self) -> bool:
        return self._tool is not None

    def start(self) -> bool:
        """Start the LanguageTool server. Returns True on success."""
        if self._tool is not None:
            return True
        self._start_attempted = True
        cfg = self._settings.grammar
        java_info = self._java.ensure_java(allow_download=cfg.auto_download_java)
        if java_info is None:
            logger.warning(
                "No compatible Java runtime (17+) found. Grammar correction "
                "will be limited to basic cleanup."
            )
            return False
        self._java.apply_environment(java_info)
        try:
            import language_tool_python  # deferred heavy import

            logger.info(f"Starting LanguageTool ({cfg.language}) — this takes a few seconds...")
            self._tool = language_tool_python.LanguageTool(cfg.language)
            self._engine = "languagetool"
            logger.info("LanguageTool server ready")
            return True
        except Exception as exc:
            self._tool = None
            self._engine = "none"
            logger.error(f"LanguageTool failed to start: {exc}")
            return False

    def warmup(self) -> bool:
        """Start LanguageTool and run one short check.

        Starting the JVM is not enough: the first ``check()`` loads dictionaries
        and takes several seconds.  Exercising it during startup moves that cost
        away from the first dictation.  Failures degrade to basic cleanup.
        """
        if not self._settings.grammar.enabled:
            return False
        if not self.start():
            return False
        tool = self._tool
        if tool is None:  # pragma: no cover - start() guarantees a tool
            return False
        try:
            tool.check("Isto e um teste de aquecimento.")
            logger.info("LanguageTool warm-up complete")
            return True
        except Exception as exc:  # pragma: no cover - server dependent
            logger.warning(f"LanguageTool warm-up failed (non fatal): {exc}")
            return False

    def correct(self, text: str) -> GrammarResult:
        """Correct ``text``; always returns a usable result.

        Starts the LanguageTool server lazily on first use (only once — if the
        first attempt fails the engine degrades to basic cleanup).
        """
        started = time.perf_counter()
        if not text or not text.strip():
            return GrammarResult(original=text, corrected=text)

        cfg = self._settings.grammar
        if cfg.enabled and self._tool is None and not self._start_attempted:
            self.start()
        if not cfg.enabled or self._tool is None:
            cleaned = cleanup_text(text)
            return GrammarResult(
                original=text,
                corrected=cleaned,
                elapsed_s=time.perf_counter() - started,
                engine_used="cleanup" if cleaned != text else "none",
            )

        try:
            raw_matches = self._tool.check(text)
        except Exception as exc:
            logger.error(f"LanguageTool check failed: {exc}")
            cleaned = cleanup_text(text)
            return GrammarResult(
                original=text,
                corrected=cleaned,
                elapsed_s=time.perf_counter() - started,
                engine_used="cleanup",
            )

        matches = self._convert_matches(raw_matches, cfg.max_matches)
        corrected = apply_matches(text, matches)
        corrected = cleanup_text(corrected)
        result = GrammarResult(
            original=text,
            corrected=corrected,
            matches=matches,
            elapsed_s=time.perf_counter() - started,
            engine_used="languagetool",
        )
        if result.changed:
            applied = sum(1 for m in matches if m.applied)
            logger.info(f"Grammar fixed {applied} issue(s): '{corrected}'")
        return result

    # -------------------------------------------------------------- helpers
    def _convert_matches(self, raw_matches: list, limit: int) -> list[GrammarMatch]:
        converted: list[GrammarMatch] = []
        for raw in raw_matches:
            category = str(getattr(raw, "category", "") or "").upper()
            replacements = list(getattr(raw, "replacements", []) or [])
            match = GrammarMatch(
                rule_id=str(getattr(raw, "rule_id", "") or ""),
                message=str(getattr(raw, "message", "") or ""),
                replacement=replacements[0] if replacements else "",
                offset=int(getattr(raw, "offset", 0) or 0),
                length=int(getattr(raw, "error_length", 0) or 0),
                category=category,
            )
            # Auto-apply only safe categories; keep the rest as information.
            if category not in SAFE_CATEGORIES:
                match.replacement = ""
            converted.append(match)
            if len(converted) >= limit:
                break
        return converted

    def close(self) -> None:
        """Shut down the LanguageTool server (called when unloading models)."""
        tool, self._tool = self._tool, None
        self._engine = "none"
        if tool is None:
            return
        try:
            tool.close()
            logger.info("LanguageTool server stopped")
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"Error closing LanguageTool: {exc}")
