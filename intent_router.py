"""
intent_router.py — Centralised semantic Intent Router for Spikerabot.

Routing precedence
------------------
1.  Exact / configured fast-path triggers (no LLM call, confidence = 1.0)
        • web-search trigger phrases from config.xml
        • image-generation hardcoded keywords
        • memory-summary trigger phrases from config.xml
        • file-summary  trigger phrases from config.xml
2.  Semantic classifier (single Ollama call at temperature=0)
        • receives current message + last N conversation turns
        • returns structured JSON
        • result is accepted only when confidence >= threshold
3.  Fallback → NORMAL_CHAT (safe, never crashes)

The router decides WHAT to do, not HOW.  It never generates the final
user-facing answer.

Limitation
----------
Multi-intent messages (e.g. "draw a picture of today's headlines") are
resolved by choosing the dominant intent in the precedence order above.
Full multi-intent planning is out of scope.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from config_loader import load_config
from debug_logger import debug_logger


# ---------------------------------------------------------------------------
# Intent taxonomy
# ---------------------------------------------------------------------------

class IntentType(Enum):
    NORMAL_CHAT           = "normal_chat"
    WEB_SEARCH_EXPLICIT   = "web_search_explicit"   # user explicitly asks to search
    WEB_SEARCH_FRESHNESS  = "web_search_freshness"  # answer needs current data
    IMAGE_GENERATION      = "image_generation"
    SUMMARY_MEMORY        = "summary_memory"        # summarise in-memory context
    SUMMARY_FILE          = "summary_file"          # summarise persisted log files


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class IntentResult:
    intent:     IntentType
    confidence: float
    query:      Optional[str] = None   # cleaned search query when applicable
    explicit:   bool          = False  # True when the user explicitly said "search"
    reason:     Optional[str] = None   # human-readable explanation (for logging)
    source:     str           = "fallback"
    # source values:  "exact_trigger" | "semantic_classifier" | "fallback"


# ---------------------------------------------------------------------------
# Classifier prompt
# ---------------------------------------------------------------------------

_CLASSIFIER_PROMPT_TEMPLATE = """\
You are an intent classifier for a Telegram assistant called Spikerabot.
Your job is to decide what the user wants operationally so the right subsystem handles it.

IMPORTANT: classify by MEANING, not by exact wording.  The user writes in Russian.

=== INTENTS ===

normal_chat
  The message can be answered from conversation context, internal knowledge or documents.
  Examples: greetings, historical/philosophical questions, code questions, opinions.

web_search_explicit
  The user EXPLICITLY asks to search, find, look up, verify, google, check online, browse
  the internet, inspect external sources, etc.  Classify by semantic intent, not vocabulary.
  Set explicit=true.
  Examples (all mean "search the web"):
    - найди в интернете X
    - поищи информацию про X
    - погугли X
    - разыщи в сети X
    - проверь в интернете правда ли X
    - посмотри что пишут о X
    - глянь последние данные по X
    - не могли бы вы найти в интернете X

web_search_freshness
  The user does NOT explicitly request a search, but a reliable answer requires
  current or rapidly-changing information: news, weather, prices, exchange rates,
  sports results, software versions, current officeholders, recent events, schedules.
  Set explicit=false.
  Examples:
    - кто сейчас премьер-министр Канады?
    - какая сейчас цена биткоина?
    - последняя стабильная версия PostgreSQL?
    - что произошло сегодня в Берлине?

image_generation
  The user asks to create, draw, generate or show an image.

summary_memory
  The user asks for a summary of the current in-memory conversation.

summary_file
  The user asks for a summary based on persisted chat logs or history files.

=== RECENT CONVERSATION (for resolving pronouns / references) ===
{conversation_context}

=== CURRENT MESSAGE ===
{message}

=== INSTRUCTIONS ===
Return ONLY valid JSON, no markdown, no explanation:
{{
  "intent": "<one of the intent names above>",
  "confidence": <0.0–1.0>,
  "query": "<concise search query in the same language as the message, or null>",
  "explicit": <true|false>,
  "reason": "<one short English sentence>"
}}

For query: extract only the subject of the search, strip persona/addressing words.
For normal_chat or non-search intents set query to null.
"""

# ---------------------------------------------------------------------------
# Hardcoded image trigger keywords (mirrors image_generator.py)
# ---------------------------------------------------------------------------
_IMAGE_TRIGGERS = frozenset([
    'картинка', 'изображение', 'фото', 'рисунок', 'нарисуй', 'покажи',
])

# Natural explicit-search wording must not depend on the LLM classifier.
# Requiring both an action and a web-related noun keeps this conservative:
# "найти смысл жизни" remains chat, while "найти сайт/ссылку" is search.
_SEARCH_ACTION_RE = re.compile(
    r"\b(?:найти|найди|найдите|поищи|поищите|разыщи|разыщите|"
    r"погугли|погуглите|загугли|загуглите|проверь|проверьте|"
    r"посмотри|посмотрите|отыщи|отыщите)\b",
    re.IGNORECASE,
)
_WEB_REFERENCE_RE = re.compile(
    r"\b(?:интернет\w*|онлайн|веб\w*|сеть|сети|сайт\w*|ссылк\w*)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Main router class
# ---------------------------------------------------------------------------

class IntentRouter:
    """Classifies a user message into a structured IntentResult.

    Usage::

        router = IntentRouter()
        result = router.classify(text, recent_history)
        # result.intent, result.query, result.source, ...
    """

    def __init__(self) -> None:
        self._config = load_config()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(
        self,
        text: str,
        conversation_history: Optional[List[Dict]] = None,
    ) -> IntentResult:
        """Return an IntentResult for *text*.

        Always succeeds — falls back to NORMAL_CHAT on any error.

        Args:
            text: The raw user message.
            conversation_history: Full history list (recent tail is selected
                                  internally based on config context_turns).
        """

        # 1. Fast-path exact triggers — no LLM call
        fast = self._fast_path(text)
        if fast is not None:
            self._log(fast)
            return fast

        # 2. If router is disabled, fall back immediately
        if not self._config.intent_router_enabled:
            result = IntentResult(
                intent=IntentType.NORMAL_CHAT,
                confidence=1.0,
                source="fallback",
                reason="intent_router disabled in config",
            )
            self._log(result)
            return result

        # 3. Semantic classifier
        try:
            result = self._classify_semantic(text, conversation_history or [])
        except Exception as exc:  # noqa: BLE001
            debug_logger.log_error(f"IntentRouter: classifier failed: {exc}", exc)
            result = IntentResult(
                intent=IntentType.NORMAL_CHAT,
                confidence=0.0,
                source="fallback",
                reason=f"classifier error: {exc}",
            )

        self._log(result)
        return result

    # ------------------------------------------------------------------
    # Fast-path exact triggers
    # ------------------------------------------------------------------

    def _fast_path(self, text: str) -> Optional[IntentResult]:
        """Check all configured / hardcoded triggers without calling the LLM.

        Returns an IntentResult if any trigger matches, else None.
        """
        text_lower = text.lower()

        # Web search explicit triggers from config.xml
        if self._config.web_search_enabled:
            for trigger in self._config.web_search_triggers:
                if trigger.lower() in text_lower:
                    return IntentResult(
                        intent=IntentType.WEB_SEARCH_EXPLICIT,
                        confidence=1.0,
                        query=self._strip_trigger(text, trigger),
                        explicit=True,
                        source="exact_trigger",
                        reason=f"matched configured trigger '{trigger}'",
                    )

            # Catch natural requests whose action and web reference are
            # separated: "найти канадский сайт ... в Интернете".
            if _SEARCH_ACTION_RE.search(text) and _WEB_REFERENCE_RE.search(text):
                return IntentResult(
                    intent=IntentType.WEB_SEARCH_EXPLICIT,
                    confidence=1.0,
                    query=self._extract_explicit_search_query(text),
                    explicit=True,
                    source="exact_trigger",
                    reason="matched explicit web-search wording",
                )

        # Image generation hardcoded keywords — match as word stems
        # Use substring matching on lowercased text (same as original image_generator.py)
        # We also check inflected forms by testing if any trigger appears within a word
        for kw in _IMAGE_TRIGGERS:
            # Check both exact substring and simple prefix match for Russian inflection
            # e.g. "картинка" should match "картинку", "картинки", "картинке"
            if kw in text_lower or any(
                word.startswith(kw[:max(4, len(kw)-2)])
                for word in text_lower.split()
            ):
                return IntentResult(
                    intent=IntentType.IMAGE_GENERATION,
                    confidence=1.0,
                    explicit=True,
                    source="exact_trigger",
                    reason=f"matched image keyword '{kw}'",
                )

        # Memory-summary triggers
        for trigger in self._config.memory_summary_triggers:
            if trigger.lower() in text_lower:
                return IntentResult(
                    intent=IntentType.SUMMARY_MEMORY,
                    confidence=1.0,
                    explicit=True,
                    source="exact_trigger",
                    reason=f"matched memory-summary trigger '{trigger}'",
                )

        # File-summary triggers
        for trigger in self._config.file_summary_triggers:
            if trigger.lower() in text_lower:
                return IntentResult(
                    intent=IntentType.SUMMARY_FILE,
                    confidence=1.0,
                    explicit=True,
                    source="exact_trigger",
                    reason=f"matched file-summary trigger '{trigger}'",
                )

        return None

    # ------------------------------------------------------------------
    # Semantic classifier
    # ------------------------------------------------------------------

    def _classify_semantic(
        self,
        text: str,
        conversation_history: List[Dict],
    ) -> IntentResult:
        """Ask the local LLM to classify the intent at temperature=0."""
        from model import raw_llm_call  # local import avoids circular dep at module load

        # Build a small conversation snippet for pronoun resolution
        turns = self._config.intent_router_context_turns
        recent = conversation_history[-turns * 2:] if turns > 0 else []
        conv_lines = []
        for msg in recent:
            role = "User" if msg.get('role') == 'user' else "Bot"
            content = msg.get('content', '')[:200]  # cap length
            conv_lines.append(f"{role}: {content}")
        conversation_context = "\n".join(conv_lines) if conv_lines else "(none)"

        prompt = _CLASSIFIER_PROMPT_TEMPLATE.format(
            conversation_context=conversation_context,
            message=text,
        )

        timeout = self._config.intent_router_classifier_timeout
        raw = raw_llm_call(prompt, temperature=0.0, timeout=timeout)

        return self._parse_classifier_response(raw, text)

    # ------------------------------------------------------------------
    # Response parser — robust against every kind of LLM misbehaviour
    # ------------------------------------------------------------------

    def _parse_classifier_response(self, raw: str, original_text: str) -> IntentResult:
        """Parse the classifier's JSON response into an IntentResult.

        Handles:
        - markdown code fences
        - trailing commas / minor JSON quirks
        - missing fields
        - unknown intent values
        - empty response
        """
        threshold = self._config.intent_router_confidence_threshold

        # Strip markdown fences
        cleaned = re.sub(r'```(?:json)?\s*', '', raw, flags=re.IGNORECASE)
        cleaned = re.sub(r'```', '', cleaned).strip()

        # Extract the first JSON object in the response
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if not json_match:
            debug_logger.log_info(
                f"IntentRouter: no JSON found in classifier response: {raw[:200]}"
            )
            return self._fallback()

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            # Try stripping trailing commas (common LLM mistake)
            fixed = re.sub(r',\s*([}\]])', r'\1', json_match.group())
            try:
                data = json.loads(fixed)
            except json.JSONDecodeError as exc:
                debug_logger.log_info(
                    f"IntentRouter: JSON parse error: {exc} — raw: {raw[:200]}"
                )
                return self._fallback()

        # Validate intent
        intent_str = str(data.get('intent', '')).lower()
        try:
            intent = IntentType(intent_str)
        except ValueError:
            debug_logger.log_info(
                f"IntentRouter: unknown intent value '{intent_str}', falling back"
            )
            return self._fallback()

        confidence = float(data.get('confidence', 0.0))

        # WEB_SEARCH_FRESHNESS requires smart_search to be enabled
        if intent == IntentType.WEB_SEARCH_FRESHNESS and not self._config.smart_search_enabled:
            debug_logger.log_info(
                "IntentRouter: WEB_SEARCH_FRESHNESS suppressed (smart_search disabled)"
            )
            return IntentResult(
                intent=IntentType.NORMAL_CHAT,
                confidence=1.0,
                source="fallback",
                reason="smart_search_enabled=false suppresses freshness search",
            )

        # Low confidence → fall back
        if confidence < threshold:
            debug_logger.log_info(
                f"IntentRouter: confidence {confidence:.2f} < threshold {threshold:.2f} "
                f"for intent '{intent_str}', falling back to NORMAL_CHAT"
            )
            return IntentResult(
                intent=IntentType.NORMAL_CHAT,
                confidence=confidence,
                source="fallback",
                reason=f"confidence below threshold ({confidence:.2f} < {threshold:.2f})",
            )

        query = data.get('query') or None
        # If the router suggests a search but produced no query, use original text
        if intent in (IntentType.WEB_SEARCH_EXPLICIT, IntentType.WEB_SEARCH_FRESHNESS):
            if not query:
                query = original_text

        return IntentResult(
            intent=intent,
            confidence=confidence,
            query=query,
            explicit=bool(data.get('explicit', False)),
            reason=data.get('reason'),
            source="semantic_classifier",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_trigger(text: str, trigger: str) -> str:
        """Remove the trigger phrase from the message and clean up surrounding noise.

        Example:
            "Сталин, поиск в интернете курс рубля"
            → remove "поиск в интернете"
            → "Сталин,  курс рубля"
            → strip punctuation/whitespace
            → "Сталин, курс рубля"
        """
        stripped = re.sub(re.escape(trigger), '', text, flags=re.IGNORECASE)
        # Collapse multiple spaces and strip leading/trailing punctuation + whitespace
        stripped = re.sub(r'[ \t]{2,}', ' ', stripped)
        stripped = stripped.strip(' \t\n\r,.')
        return stripped if stripped else text

    @staticmethod
    def _extract_explicit_search_query(text: str) -> str:
        """Extract the subject from a deterministic explicit-search match."""
        action = _SEARCH_ACTION_RE.search(text)
        if action is None:
            return text

        query = text[action.end():]
        query = re.sub(
            r"^\s*(?:мне\s+|для\s+меня\s+)?(?:пожалуйста[,.]?\s*)?",
            "",
            query,
            flags=re.IGNORECASE,
        )
        query = re.sub(
            r"^\s*(?:(?:в|во)\s+(?:интернет\w*|сети|сеть)|онлайн)\s*[,.:;-]?\s*",
            "",
            query,
            flags=re.IGNORECASE,
        )
        query = re.sub(
            r"\s+(?:(?:в|во)\s+(?:интернет\w*|сети|сеть)|онлайн)\s*[?.!]*$",
            "",
            query,
            flags=re.IGNORECASE,
        )
        query = re.sub(r'[ \t]{2,}', ' ', query).strip(' \t\n\r,.:;!?-')
        return query if query else text

    @staticmethod
    def _fallback() -> IntentResult:
        return IntentResult(
            intent=IntentType.NORMAL_CHAT,
            confidence=0.0,
            source="fallback",
            reason="classifier produced unreadable output",
        )

    def _log(self, result: IntentResult) -> None:
        """Emit a concise routing decision to the debug log."""
        debug_logger.log_info(
            f"IntentRouter: intent={result.intent.value} "
            f"confidence={result.confidence:.2f} "
            f"source={result.source} "
            f"explicit={result.explicit} "
            f"query={result.query!r} "
            f"reason={result.reason!r}"
        )


# ---------------------------------------------------------------------------
# Module-level singleton — import and use directly
# ---------------------------------------------------------------------------
intent_router = IntentRouter()
