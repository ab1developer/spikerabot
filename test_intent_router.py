"""
test_intent_router.py — Tests for the IntentRouter.

Run with:
    python -m pytest test_intent_router.py -v
or:
    python test_intent_router.py

Tests are split into:
1.  Fast-path (exact triggers) — no Ollama required.
2.  Semantic classifier — Ollama is mocked.
3.  Failure / degradation — timeout, bad JSON, unknown intent, etc.
4.  Freshness suppression — smart_search_enabled=False.
5.  Query rewriting sanity checks.
"""

from __future__ import annotations

import json
import sys
import types
import unittest
from dataclasses import dataclass
from typing import List, Dict, Optional
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Minimal stubs so we can import intent_router without a real Ollama / config
# ---------------------------------------------------------------------------

def _make_config(
    *,
    router_enabled: bool = True,
    threshold: float = 0.70,
    context_turns: int = 2,
    classifier_timeout: int = 15,
    smart_search_enabled: bool = True,
    web_search_enabled: bool = True,
    web_search_triggers: Optional[List[str]] = None,
    memory_summary_triggers: Optional[List[str]] = None,
    file_summary_triggers: Optional[List[str]] = None,
):
    cfg = MagicMock()
    cfg.intent_router_enabled = router_enabled
    cfg.intent_router_confidence_threshold = threshold
    cfg.intent_router_context_turns = context_turns
    cfg.intent_router_classifier_timeout = classifier_timeout
    cfg.smart_search_enabled = smart_search_enabled
    cfg.web_search_enabled = web_search_enabled
    cfg.web_search_triggers = web_search_triggers or [
        'поиск в интернете',
        'найди в сети',
        'что в интернете',
    ]
    cfg.memory_summary_triggers = memory_summary_triggers or [
        'бот, резюме',
        'бот, саммари',
        'бот, итог',
        'бот, кратко',
        'бот, что обсуждали',
        'бот, о чем говорили',
    ]
    cfg.file_summary_triggers = file_summary_triggers or [
        'бот, резюме файлов',
        'бот, логи',
        'бот, история чата',
    ]
    return cfg


def _stub_modules():
    """Insert lightweight stub modules so intent_router can be imported."""
    # debug_logger stub
    dl = types.ModuleType('debug_logger')
    logger = MagicMock()
    dl.debug_logger = logger
    sys.modules.setdefault('debug_logger', dl)

    # config_loader stub — returns a default config
    cl = types.ModuleType('config_loader')
    cl.load_config = lambda: _make_config()
    sys.modules['config_loader'] = cl

    # model stub
    m = types.ModuleType('model')
    m.raw_llm_call = MagicMock(return_value='{"intent":"normal_chat","confidence":0.9,"query":null,"explicit":false,"reason":"stub"}')
    sys.modules.setdefault('model', m)


_stub_modules()

# Now we can import
from intent_router import IntentRouter, IntentType, IntentResult  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_router(cfg=None) -> IntentRouter:
    router = IntentRouter.__new__(IntentRouter)
    router._config = cfg or _make_config()
    return router


def _ollama_response(
    intent: str,
    confidence: float,
    query: Optional[str] = None,
    explicit: bool = False,
    reason: str = "test",
) -> str:
    return json.dumps({
        "intent": intent,
        "confidence": confidence,
        "query": query,
        "explicit": explicit,
        "reason": reason,
    })


# ---------------------------------------------------------------------------
# 1. Fast-path tests
# ---------------------------------------------------------------------------

class TestFastPath(unittest.TestCase):

    def setUp(self):
        self.router = _make_router()

    def _assert_fast(self, text: str, expected_intent: IntentType):
        result = self.router._fast_path(text)
        self.assertIsNotNone(result, f"Expected fast-path match for: {text!r}")
        self.assertEqual(result.intent, expected_intent)
        self.assertEqual(result.source, "exact_trigger")
        self.assertEqual(result.confidence, 1.0)

    # --- Web search exact triggers ---

    def test_web_trigger_phrase_1(self):
        self._assert_fast("поиск в интернете курс доллара", IntentType.WEB_SEARCH_EXPLICIT)

    def test_web_trigger_phrase_2(self):
        self._assert_fast("найди в сети последние новости", IntentType.WEB_SEARCH_EXPLICIT)

    def test_web_trigger_phrase_3(self):
        self._assert_fast("что в интернете пишут об этом?", IntentType.WEB_SEARCH_EXPLICIT)

    def test_web_trigger_case_insensitive(self):
        self._assert_fast("ПОИСК В ИНТЕРНЕТЕ PostgreSQL", IntentType.WEB_SEARCH_EXPLICIT)

    def test_web_trigger_in_longer_sentence(self):
        self._assert_fast(
            "Товарищ Сталин, поиск в интернете, что происходит на фронте",
            IntentType.WEB_SEARCH_EXPLICIT,
        )

    # --- Image triggers ---

    def test_image_trigger_нарисуй(self):
        self._assert_fast("нарисуй красный трактор", IntentType.IMAGE_GENERATION)

    def test_image_trigger_картинка(self):
        self._assert_fast("хочу картинку с котом", IntentType.IMAGE_GENERATION)

    def test_image_trigger_изображение(self):
        self._assert_fast("создай изображение горы", IntentType.IMAGE_GENERATION)

    # --- Summary triggers ---

    def test_memory_summary_резюме(self):
        self._assert_fast("бот, резюме нашего разговора", IntentType.SUMMARY_MEMORY)

    def test_memory_summary_итог(self):
        self._assert_fast("бот, итог", IntentType.SUMMARY_MEMORY)

    def test_file_summary_логи(self):
        self._assert_fast("бот, логи за последние 2 часа", IntentType.SUMMARY_FILE)

    def test_file_summary_история(self):
        self._assert_fast("бот, история чата", IntentType.SUMMARY_FILE)

    # --- No match returns None ---

    def test_no_match_normal_question(self):
        result = self.router._fast_path("объясни мне MVCC в PostgreSQL")
        self.assertIsNone(result)

    def test_no_match_greeting(self):
        result = self.router._fast_path("Привет, как дела?")
        self.assertIsNone(result)

    # --- Query stripping ---

    def test_query_stripping_removes_trigger(self):
        result = self.router._fast_path("поиск в интернете курс доллара")
        self.assertIsNotNone(result)
        self.assertNotIn("поиск в интернете", result.query.lower())

    # --- web_search_enabled=False disables web triggers ---

    def test_web_trigger_disabled_when_search_off(self):
        cfg = _make_config(web_search_enabled=False)
        router = _make_router(cfg)
        result = router._fast_path("поиск в интернете курс рубля")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# 2. Semantic classifier — Ollama mocked
# ---------------------------------------------------------------------------

class TestSemanticClassifier(unittest.TestCase):

    def _classify(
        self,
        text: str,
        ollama_returns: str,
        smart_search_enabled: bool = True,
        threshold: float = 0.70,
        history: Optional[List[Dict]] = None,
    ) -> IntentResult:
        cfg = _make_config(
            smart_search_enabled=smart_search_enabled,
            threshold=threshold,
        )
        router = _make_router(cfg)

        import model as m
        with patch.object(m, 'raw_llm_call', return_value=ollama_returns):
            return router._classify_semantic(text, history or [])

    # --- Explicit web search ---

    def test_explicit_web_найди(self):
        resp = _ollama_response("web_search_explicit", 0.98, "PostgreSQL 19 release", True)
        result = self._classify("найди в интернете последние новости о PostgreSQL", resp)
        self.assertEqual(result.intent, IntentType.WEB_SEARCH_EXPLICIT)
        self.assertGreaterEqual(result.confidence, 0.70)
        self.assertEqual(result.source, "semantic_classifier")

    def test_explicit_web_посмотри(self):
        resp = _ollama_response("web_search_explicit", 0.95, "информация об этом", True)
        result = self._classify("посмотри в сети информацию об этом", resp)
        self.assertEqual(result.intent, IntentType.WEB_SEARCH_EXPLICIT)

    def test_explicit_web_погугли(self):
        resp = _ollama_response("web_search_explicit", 0.97, "история проекта", True)
        result = self._classify("погугли историю этого проекта", resp)
        self.assertEqual(result.intent, IntentType.WEB_SEARCH_EXPLICIT)

    def test_explicit_web_проверь(self):
        resp = _ollama_response("web_search_explicit", 0.92, "правда ли это", True)
        result = self._classify("проверь в интернете, правда ли это", resp)
        self.assertEqual(result.intent, IntentType.WEB_SEARCH_EXPLICIT)

    def test_explicit_web_formal_address(self):
        resp = _ollama_response("web_search_explicit", 0.96, "вот это", True)
        result = self._classify(
            "Товарищ Сталин, а не могли бы вы мне найти в Интернете вот это", resp
        )
        self.assertEqual(result.intent, IntentType.WEB_SEARCH_EXPLICIT)

    def test_explicit_web_formal_разыщите(self):
        resp = _ollama_response("web_search_explicit", 0.94, "сведения о реакторе", True)
        result = self._classify("разыщите-ка мне свежие сведения о реакторе", resp)
        self.assertEqual(result.intent, IntentType.WEB_SEARCH_EXPLICIT)

    def test_explicit_web_глянь(self):
        resp = _ollama_response("web_search_explicit", 0.91, "что пишут об этом", True)
        result = self._classify("глянь, что пишут об этом в сети", resp)
        self.assertEqual(result.intent, IntentType.WEB_SEARCH_EXPLICIT)

    def test_explicit_web_worldwideweb(self):
        resp = _ollama_response("web_search_explicit", 0.89, "это", True)
        result = self._classify(
            "не соблаговолите ли вы разыскать это во всемирной паутине?", resp
        )
        self.assertEqual(result.intent, IntentType.WEB_SEARCH_EXPLICIT)

    def test_explicit_web_нынче_пишут(self):
        resp = _ollama_response("web_search_explicit", 0.88, "об этом", True)
        result = self._classify("можно узнать, что об этом нынче пишут?", resp)
        self.assertEqual(result.intent, IntentType.WEB_SEARCH_EXPLICIT)

    def test_explicit_web_внешние_источники(self):
        resp = _ollama_response("web_search_explicit", 0.87, None, True)
        result = self._classify("товарищ Сталин, проверьте внешние источники", resp)
        self.assertEqual(result.intent, IntentType.WEB_SEARCH_EXPLICIT)

    # --- Freshness search ---

    def test_freshness_премьер(self):
        resp = _ollama_response("web_search_freshness", 0.90, "current prime minister Canada")
        result = self._classify("кто сейчас премьер-министр Канады?", resp)
        self.assertEqual(result.intent, IntentType.WEB_SEARCH_FRESHNESS)

    def test_freshness_биткоин(self):
        resp = _ollama_response("web_search_freshness", 0.95, "bitcoin price now")
        result = self._classify("какая сейчас цена биткоина?", resp)
        self.assertEqual(result.intent, IntentType.WEB_SEARCH_FRESHNESS)

    def test_freshness_postgresql_version(self):
        resp = _ollama_response("web_search_freshness", 0.88, "latest stable PostgreSQL version")
        result = self._classify("какая последняя стабильная версия PostgreSQL?", resp)
        self.assertEqual(result.intent, IntentType.WEB_SEARCH_FRESHNESS)

    def test_freshness_events(self):
        resp = _ollama_response("web_search_freshness", 0.91, "today events Berlin")
        result = self._classify("что произошло сегодня в Берлине?", resp)
        self.assertEqual(result.intent, IntentType.WEB_SEARCH_FRESHNESS)

    def test_freshness_disabled_when_smart_search_off(self):
        resp = _ollama_response("web_search_freshness", 0.91, "bitcoin price")
        result = self._classify("какая сейчас цена биткоина?", resp, smart_search_enabled=False)
        # Must fall back to NORMAL_CHAT
        self.assertEqual(result.intent, IntentType.NORMAL_CHAT)

    # --- Normal chat (must NOT trigger search) ---

    def test_normal_mvcc(self):
        resp = _ollama_response("normal_chat", 0.97)
        result = self._classify("объясни мне MVCC в PostgreSQL", resp)
        self.assertEqual(result.intent, IntentType.NORMAL_CHAT)

    def test_normal_historical(self):
        resp = _ollama_response("normal_chat", 0.99)
        result = self._classify("кто такой Иосиф Сталин?", resp)
        self.assertEqual(result.intent, IntentType.NORMAL_CHAT)

    def test_normal_sky_blue(self):
        resp = _ollama_response("normal_chat", 0.98)
        result = self._classify("почему небо голубое?", resp)
        self.assertEqual(result.intent, IntentType.NORMAL_CHAT)

    def test_normal_btree(self):
        resp = _ollama_response("normal_chat", 0.97)
        result = self._classify("расскажи, как работает B-tree", resp)
        self.assertEqual(result.intent, IntentType.NORMAL_CHAT)

    # --- Low confidence falls back ---

    def test_low_confidence_falls_back(self):
        resp = _ollama_response("web_search_explicit", 0.50, "something")
        result = self._classify("что-то", resp, threshold=0.70)
        self.assertEqual(result.intent, IntentType.NORMAL_CHAT)
        self.assertEqual(result.source, "fallback")

    # --- Missing query uses original text ---

    def test_missing_query_uses_original(self):
        resp = _ollama_response("web_search_explicit", 0.95, None, True)
        result = self._classify("найди это в интернете", resp)
        self.assertEqual(result.intent, IntentType.WEB_SEARCH_EXPLICIT)
        self.assertIsNotNone(result.query)


# ---------------------------------------------------------------------------
# 3. Failure / degradation tests
# ---------------------------------------------------------------------------

class TestFailureDegradation(unittest.TestCase):

    def _parse(self, raw: str, original: str = "тест") -> IntentResult:
        router = _make_router()
        return router._parse_classifier_response(raw, original)

    def test_empty_response(self):
        result = self._parse("")
        self.assertEqual(result.intent, IntentType.NORMAL_CHAT)
        self.assertEqual(result.source, "fallback")

    def test_no_json_in_response(self):
        result = self._parse("Я не могу этого сделать.")
        self.assertEqual(result.intent, IntentType.NORMAL_CHAT)

    def test_malformed_json_trailing_comma(self):
        raw = '{"intent": "normal_chat", "confidence": 0.9, "query": null, "explicit": false,}'
        result = self._parse(raw)
        self.assertEqual(result.intent, IntentType.NORMAL_CHAT)

    def test_json_in_markdown_fences(self):
        raw = '```json\n{"intent":"normal_chat","confidence":0.9,"query":null,"explicit":false,"reason":"ok"}\n```'
        result = self._parse(raw)
        self.assertEqual(result.intent, IntentType.NORMAL_CHAT)
        self.assertNotEqual(result.source, "fallback")  # should parse successfully

    def test_unknown_intent_value(self):
        raw = '{"intent":"fly_to_the_moon","confidence":0.99,"query":null,"explicit":false,"reason":"?"}'
        result = self._parse(raw)
        self.assertEqual(result.intent, IntentType.NORMAL_CHAT)
        self.assertEqual(result.source, "fallback")

    def test_missing_confidence_field(self):
        raw = '{"intent":"normal_chat","query":null,"explicit":false,"reason":"ok"}'
        result = self._parse(raw)
        # confidence defaults to 0.0 → falls back because 0.0 < threshold
        self.assertEqual(result.intent, IntentType.NORMAL_CHAT)

    def test_missing_query_field(self):
        raw = '{"intent":"web_search_explicit","confidence":0.95,"explicit":true,"reason":"ok"}'
        result = self._parse(raw, "найди что-нибудь")
        self.assertEqual(result.intent, IntentType.WEB_SEARCH_EXPLICIT)
        # query should fall back to original text
        self.assertEqual(result.query, "найди что-нибудь")

    def test_ollama_timeout_returns_fallback(self):
        cfg = _make_config()
        router = _make_router(cfg)

        import model as m
        with patch.object(m, 'raw_llm_call', side_effect=TimeoutError("timed out")):
            result = router.classify("поищи информацию про PostgreSQL")

        # Fast-path should NOT catch this (no exact trigger matches)
        # → classifier raises → fallback
        self.assertEqual(result.intent, IntentType.NORMAL_CHAT)
        self.assertEqual(result.source, "fallback")

    def test_ollama_exception_returns_fallback(self):
        cfg = _make_config()
        router = _make_router(cfg)

        import model as m
        with patch.object(m, 'raw_llm_call', side_effect=ConnectionError("refused")):
            result = router.classify("скажи мне последние новости")

        self.assertEqual(result.intent, IntentType.NORMAL_CHAT)
        self.assertEqual(result.source, "fallback")

    def test_router_never_raises(self):
        """classify() must never propagate an exception to the caller."""
        cfg = _make_config()
        router = _make_router(cfg)

        import model as m
        with patch.object(m, 'raw_llm_call', side_effect=RuntimeError("boom")):
            try:
                result = router.classify("anything")
            except Exception as exc:
                self.fail(f"classify() raised an exception: {exc}")

        self.assertIsInstance(result, IntentResult)


# ---------------------------------------------------------------------------
# 4. Router disabled
# ---------------------------------------------------------------------------

class TestRouterDisabled(unittest.TestCase):

    def test_disabled_router_returns_normal_chat_without_llm(self):
        cfg = _make_config(router_enabled=False)
        router = _make_router(cfg)

        # Track whether _classify_semantic was entered by checking
        # that raw_llm_call is never invoked.
        # "найди свежие данные про это" has no exact configured trigger
        # so it must hit the disabled-check branch and return NORMAL_CHAT
        # without calling the LLM.
        called = []
        original = router._classify_semantic

        def spy(*args, **kwargs):
            called.append(True)
            return original(*args, **kwargs)

        router._classify_semantic = spy

        result = router.classify("найди свежие данные про это")

        self.assertEqual(len(called), 0, "_classify_semantic should not be called when router is disabled")
        self.assertEqual(result.intent, IntentType.NORMAL_CHAT)

    def test_disabled_router_still_uses_fast_path(self):
        """Even with router disabled, exact triggers still fire."""
        cfg = _make_config(router_enabled=False)
        router = _make_router(cfg)
        result = router.classify("поиск в интернете биткоин")
        # Fast-path fires before the disabled check
        self.assertEqual(result.intent, IntentType.WEB_SEARCH_EXPLICIT)
        self.assertEqual(result.source, "exact_trigger")


# ---------------------------------------------------------------------------
# 5. Query rewriting
# ---------------------------------------------------------------------------

class TestQueryRewriting(unittest.TestCase):

    def _classify_with_mock(self, text: str, ollama_query: str) -> IntentResult:
        cfg = _make_config()
        router = _make_router(cfg)
        resp = _ollama_response("web_search_explicit", 0.95, ollama_query, True)
        import model as m
        with patch.object(m, 'raw_llm_call', return_value=resp):
            return router._classify_semantic(text, [])

    def test_strip_persona_from_query(self):
        result = self._classify_with_mock(
            "Товарищ Сталин, вы не могли бы посмотреть в этих ваших интернетах, "
            "какая сейчас последняя стабильная версия PostgreSQL?",
            "latest stable PostgreSQL version",
        )
        self.assertEqual(result.query, "latest stable PostgreSQL version")
        self.assertNotIn("Сталин", result.query)

    def test_preserve_technical_terms(self):
        result = self._classify_with_mock(
            "найди в интернете PostgreSQL 19 release date",
            "PostgreSQL 19 release date",
        )
        self.assertEqual(result.query, "PostgreSQL 19 release date")

    def test_fast_path_query_strips_trigger(self):
        cfg = _make_config()
        router = _make_router(cfg)
        result = router._fast_path("поиск в интернете цена биткоина")
        self.assertIsNotNone(result)
        self.assertNotIn("поиск в интернете", result.query.lower())
        self.assertIn("цена биткоина", result.query)

    def test_natural_search_request_with_trailing_web_reference(self):
        cfg = _make_config()
        router = _make_router(cfg)
        result = router._fast_path(
            "это нормально. А теперь попробуйте мне найти канадский сайт "
            "магазина Амазон в Интернете"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.intent, IntentType.WEB_SEARCH_EXPLICIT)
        self.assertEqual(result.source, "exact_trigger")
        self.assertEqual(result.query, "канадский сайт магазина Амазон")

    def test_natural_search_request_strips_leading_web_reference(self):
        cfg = _make_config()
        router = _make_router(cfg)
        result = router._fast_path("найдите мне в интернете сайт Amazon Canada")
        self.assertIsNotNone(result)
        self.assertEqual(result.intent, IntentType.WEB_SEARCH_EXPLICIT)
        self.assertEqual(result.query, "сайт Amazon Canada")


# ---------------------------------------------------------------------------
# 6. Conversation context is passed correctly
# ---------------------------------------------------------------------------

class TestConversationContext(unittest.TestCase):

    def test_context_turns_respected(self):
        """Router should pass only the last N*2 messages to the classifier."""
        cfg = _make_config(context_turns=2)
        router = _make_router(cfg)

        history = [
            {'role': 'user', 'content': f'msg {i}'} for i in range(10)
        ]

        captured_prompts = []

        def fake_llm(prompt, **kwargs):
            captured_prompts.append(prompt)
            return _ollama_response("normal_chat", 0.9)

        import model as m
        with patch.object(m, 'raw_llm_call', side_effect=fake_llm):
            router._classify_semantic("test", history)

        self.assertEqual(len(captured_prompts), 1)
        prompt = captured_prompts[0]
        # Only last 4 messages (2 turns × 2 role slots) should appear
        self.assertIn("msg 9", prompt)
        self.assertIn("msg 8", prompt)
        self.assertIn("msg 7", prompt)
        self.assertIn("msg 6", prompt)
        self.assertNotIn("msg 5", prompt)

    def test_empty_history_ok(self):
        cfg = _make_config()
        router = _make_router(cfg)
        resp = _ollama_response("normal_chat", 0.9)
        import model as m
        with patch.object(m, 'raw_llm_call', return_value=resp):
            result = router._classify_semantic("привет", [])
        self.assertEqual(result.intent, IntentType.NORMAL_CHAT)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    unittest.main(verbosity=2)
