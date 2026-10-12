import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from web_search import WebSearcher


def _make_searcher():
    searcher = WebSearcher.__new__(WebSearcher)
    searcher.config = SimpleNamespace(
        web_search_enabled=True,
        web_search_triggers=[],
        web_search_max_results=3,
        parallel_extraction_workers=2,
        smart_search_links=3,
        embedding_model="unused",
    )
    searcher.smart_search_enabled = True
    searcher.headers = {"User-Agent": "test"}
    searcher.search_sources = [{"name": "duckduckgo", "priority": 1}]
    searcher.semantic_ranking = False
    searcher.embedding_model = None
    searcher._embedding_load_attempted = False
    searcher._search_cache = {}
    searcher._cache_ttl = 300
    return searcher


class TestUrlNormalization(unittest.TestCase):
    def setUp(self):
        self.searcher = _make_searcher()

    def test_accepts_absolute_and_protocol_relative_urls(self):
        self.assertEqual(
            self.searcher._normalize_url("//www.amazon.ca/"),
            "https://www.amazon.ca/",
        )
        self.assertEqual(
            self.searcher._normalize_url("amazon.ca"),
            "https://amazon.ca",
        )

    def test_rejects_search_navigation_and_invalid_urls(self):
        self.assertEqual(self.searcher._normalize_url("/goggles?q=test"), "")
        self.assertEqual(self.searcher._normalize_url("https:///help/discussions"), "")
        self.assertEqual(self.searcher._normalize_url(""), "")


class TestSearchBehaviour(unittest.TestCase):
    def setUp(self):
        self.searcher = _make_searcher()

    def test_empty_results_are_not_cached_and_retry(self):
        with patch.object(
            self.searcher,
            "_perform_search",
            side_effect=[("🔍 Поиск не дал результатов", []), ("ok", ["https://amazon.ca"])],
        ) as perform:
            self.assertEqual(self.searcher.search(" Amazon Canada ")[1], [])
            self.assertEqual(self.searcher.search("amazon canada")[1], ["https://amazon.ca"])
            self.assertEqual(perform.call_count, 2)

    def test_successful_results_are_cached_case_insensitively(self):
        with patch.object(
            self.searcher,
            "_perform_search",
            return_value=("ok", ["https://amazon.ca"]),
        ) as perform:
            first = self.searcher.search("Amazon Canada")
            second = self.searcher.search("  amazon   canada ")
            self.assertEqual(first, second)
            self.assertEqual(perform.call_count, 1)

    def test_no_results_skip_persona_model(self):
        fake_model = MagicMock()
        with patch.object(
            self.searcher,
            "search",
            return_value=("🔍 Поиск не дал результатов", []),
        ), patch.dict(sys.modules, {"model": fake_model}):
            result = self.searcher.search_and_analyze("Amazon Canada", [])

        self.assertEqual(result, "🔍 Поиск не дал результатов")
        fake_model.modelResponse.assert_not_called()

    def test_duckduckgo_provider_filters_invalid_rows(self):
        rows = [
            {"title": "Amazon Canada", "href": "https://www.amazon.ca/", "body": "Shop"},
            {"title": "Navigation", "href": "/goggles?q=amazon", "body": ""},
            {"title": "", "href": "https://example.com", "body": ""},
        ]
        ddgs_instance = MagicMock()
        ddgs_instance.__enter__.return_value = ddgs_instance
        ddgs_instance.__exit__.return_value = False
        ddgs_instance.text.return_value = rows

        with patch("ddgs.DDGS", return_value=ddgs_instance):
            results = self.searcher._search_duckduckgo("Amazon Canada")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://www.amazon.ca/")


if __name__ == "__main__":
    unittest.main(verbosity=2)
