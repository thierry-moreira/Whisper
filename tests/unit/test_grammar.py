"""Tests for grammar correction: cleanup, match application and degradation."""

from __future__ import annotations

from dataclasses import dataclass

from whisper_free.transcription.grammar import (
    GrammarCorrector,
    GrammarMatch,
    apply_matches,
    cleanup_text,
)


@dataclass
class FakeRawMatch:
    """Stand-in for language_tool_python.Match."""

    rule_id: str = "TEST_RULE"
    message: str = "msg"
    replacements: list = None  # type: ignore[assignment]
    offset: int = 0
    error_length: int = 1
    category: str = "TYPOS"

    def __post_init__(self):
        if self.replacements is None:
            self.replacements = ["fixed"]


class TestCleanupText:
    def test_empty(self):
        assert cleanup_text("") == ""

    def test_strip(self):
        assert cleanup_text("  olá  ") == "Olá"

    def test_collapse_spaces(self):
        assert cleanup_text("muito    bom") == "Muito bom"

    def test_space_before_punctuation_removed(self):
        assert cleanup_text("olá , tudo bem ?") == "Olá, tudo bem?"

    def test_capitalizes_first_letter(self):
        assert cleanup_text("bom dia.") == "Bom dia."

    def test_preserves_existing_punctuation(self):
        assert cleanup_text("oi!") == "Oi!"


class TestApplyMatches:
    def test_no_matches(self):
        assert apply_matches("texto", []) == "texto"

    def test_single_replacement(self):
        match = GrammarMatch(replacement="erro", offset=0, length=5)
        assert apply_matches("xxxxx", [match]) == "erro"
        assert match.applied is True

    def test_multiple_matches_right_to_left(self):
        text = "abc def"
        matches = [
            GrammarMatch(replacement="X", offset=0, length=3),  # abc -> X
            GrammarMatch(replacement="Y", offset=4, length=3),  # def -> Y
        ]
        assert apply_matches(text, matches) == "X Y"

    def test_out_of_range_offset_skipped(self):
        match = GrammarMatch(replacement="Z", offset=99, length=2)
        assert apply_matches("abc", [match]) == "abc"
        assert match.applied is False

    def test_empty_replacement_not_applied(self):
        match = GrammarMatch(replacement="", offset=0, length=1)
        assert apply_matches("abc", [match]) == "abc"


class TestGrammarCorrectorDegradation:
    """Without a running LanguageTool, correct() must fall back to cleanup."""

    def test_cleanup_fallback_when_tool_missing(self, settings):
        settings.grammar.enabled = True  # enabled but tool never started
        corrector = GrammarCorrector(settings)
        corrector._start_attempted = True  # pretend the start failed already

        result = corrector.correct("  isto  tem   erros de espaco .")
        assert result.corrected == "Isto tem erros de espaco."
        assert result.engine_used == "cleanup"

    def test_disabled_grammar_still_cleans(self, settings):
        settings.grammar.enabled = False
        corrector = GrammarCorrector(settings)
        result = corrector.correct("ola mundo")
        assert result.corrected == "Ola mundo"
        assert result.engine_used == "cleanup"

    def test_empty_text_returns_unchanged(self, settings):
        corrector = GrammarCorrector(settings)
        result = corrector.correct("")
        assert result.corrected == ""
        assert result.engine_used == "none"


class TestGrammarCorrectorWithFakeTool:
    def _make_corrector(self, settings, tool):
        corrector = GrammarCorrector(settings)
        corrector._tool = tool
        corrector._engine = "languagetool"
        corrector._start_attempted = True
        return corrector

    def test_safe_category_applied(self, settings):
        class Tool:
            def check(self, text):
                return [
                    FakeRawMatch(category="TYPOS", offset=0, error_length=4, replacements=["casa"])
                ]

        settings.grammar.enabled = True
        corrector = self._make_corrector(settings, Tool())
        result = corrector.correct("caza azul")  # "caza" -> "casa"
        assert result.corrected == "Casa azul"
        assert result.engine_used == "languagetool"

    def test_style_category_not_applied(self, settings):
        class Tool:
            def check(self, text):
                return [
                    FakeRawMatch(
                        category="STYLE", offset=0, error_length=3, replacements=["style-fix"]
                    )
                ]

        settings.grammar.enabled = True
        corrector = self._make_corrector(settings, Tool())
        result = corrector.correct("texto original")
        assert result.corrected == "Texto original"  # unchanged apart from casing
        assert result.matches[0].applied is False

    def test_tool_exception_degrades(self, settings):
        class ExplodingTool:
            def check(self, text):
                raise RuntimeError("server down")

        settings.grammar.enabled = True
        corrector = self._make_corrector(settings, ExplodingTool())
        result = corrector.correct("ola")
        assert result.corrected == "Ola"
        assert result.engine_used == "cleanup"

    def test_max_matches_limit(self, settings):
        class Tool:
            def check(self, text):
                return [FakeRawMatch(offset=0, error_length=0) for _ in range(50)]

        settings.grammar.enabled = True
        settings.grammar.max_matches = 3
        corrector = self._make_corrector(settings, Tool())
        result = corrector.correct("teste")
        assert len(result.matches) == 3
