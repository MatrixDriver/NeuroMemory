"""Tests for BM25 query sanitization."""

from neuromem.services.search import _sanitize_bm25_query


class TestSanitizeBM25Query:
    def test_plain_text_unchanged(self):
        assert _sanitize_bm25_query("hello world") == "hello world"

    def test_removes_apostrophes(self):
        result = _sanitize_bm25_query("Caroline's birthday")
        assert "'" not in result
        assert "Caroline" in result
        assert "birthday" in result

    def test_removes_smart_quotes(self):
        result = _sanitize_bm25_query("it\u2019s a \u201ctest\u201d")
        assert "\u2019" not in result
        assert "\u201c" not in result
        assert "\u201d" not in result

    def test_removes_brackets(self):
        result = _sanitize_bm25_query("test (with) [brackets] {braces}")
        assert "(" not in result
        assert ")" not in result
        assert "[" not in result
        assert "]" not in result
        assert "{" not in result
        assert "}" not in result

    def test_removes_tantivy_operators(self):
        result = _sanitize_bm25_query("test~2 word^3")
        assert "~" not in result
        assert "^" not in result

    def test_collapses_spaces(self):
        result = _sanitize_bm25_query("hello   'world'   test")
        assert "  " not in result

    def test_empty_string(self):
        assert _sanitize_bm25_query("") == ""

    def test_chinese_text_preserved(self):
        result = _sanitize_bm25_query("用户在北京工作")
        assert result == "用户在北京工作"

    def test_mixed_chinese_english(self):
        result = _sanitize_bm25_query("Caroline's 生日在5月")
        assert "Caroline" in result
        assert "生日在5月" in result
        assert "'" not in result
