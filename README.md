# Spikerabot

Advanced Telegram bot with RAG (Retrieval-Augmented Generation), Knowledge Graphs, and multi-source web search capabilities.

## Architecture Overview

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                        Telegram Bot                          │
│                      (pyTelegramBotAPI)                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
┌──────────────┐ ┌──────────┐ ┌─────────────┐
│   Telegram   │ │ Context  │ │   Message   │
│  Eligibility │ │ Manager  │ │   Logger    │
│  (triggers,  │ └────┬─────┘ └─────────────┘
│   replies)   │      │
└──────┬───────┘      ▼
       │      ┌──────────────┐
       │      │Conversations/│
       │      │  (Persistent)│
       │      └──────────────┘
       │
       ▼
┌─────────────────────────────────┐
│         Intent Router           │
│                                 │
│  1. Exact trigger fast-path     │
│  2. Semantic LLM classifier     │
│     (temperature=0, JSON out)   │
│  3. Fallback → NORMAL_CHAT      │
└──────────────┬──────────────────┘
               │
   ┌───────────┼───────────┬────────────┬────────────┐
   ▼           ▼           ▼            ▼            ▼
┌──────┐ ┌─────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐
│ RAG  │ │  Web    │ │ Image  │ │ Summary  │ │ Summary  │
│ Chat │ │ Search  │ │  Gen   │ │ (Memory) │ │  (File)  │
└──┬───┘ └────┬────┘ └────────┘ └──────────┘ └──────────┘
   │          │
   ▼          ▼
┌─────────────────────────┐
│    Ollama LLM Server    │
│   (Local Inference)     │
└─────────────────────────┘
```

### 1. **Message Processing Layer**

**main.py** - Entry point and message routing
- Handles Telegram webhook/polling
- Routes messages based on type (text, document, photo)
- Manages trigger words for group chats
- Implements reply detection

### 2. **RAG (Retrieval-Augmented Generation) System**

**rag_embeddings.py** - Document retrieval and semantic search
- **Embedding Model**: HuggingFace Transformers (sentence-transformers)
- **Vector Store**: LlamaIndex VectorStoreIndex
- **Document Processing**: Loads documents from `stalin/` folder
- **Hybrid Retrieval**: Combines vector search + knowledge graph
- **Reciprocal Rank Fusion**: Merges results from multiple sources

**Storage Structure:**
```
storage/
├── default__vector_store.json  # Vector embeddings
├── docstore.json                # Document metadata
├── graph_store.json             # Knowledge graph
└── index_store.json             # Index metadata
```

### 3. **Knowledge Graph System**

**knowledge_graph.py** - Entity extraction and relationship mapping
- **NLP Engine**: spaCy (ru_core_news_sm)
- **Entity Extraction**: Identifies people, places, organizations
- **Relationship Inference**: Uses LLM to extract semantic relationships
- **Graph Store**: LlamaIndex KnowledgeGraphIndex
- **Query Engine**: Semantic graph traversal

**Workflow:**
```
Document → spaCy NER → Entities → LLM → Triplets → Graph Store
                                    ↓
                            (Subject|Relation|Object)
```

### 4. **Web Search System**

**web_search.py** - Multi-source intelligent search
- **Search Sources**: DuckDuckGo, Brave, Google (with fallback)
- **Semantic Ranking**: Uses sentence-transformers for relevance scoring
- **Parallel Extraction**: ThreadPoolExecutor for concurrent page scraping
- **Smart Search**: LLM-based query classification
- **Caching**: LRU cache with 5-minute intervals

**Ranking Algorithm:**
```
Final Score = (Semantic Similarity × 0.7) + (Domain Authority × 0.2) + (Recency × 0.1)
```

### 5. **Context Management**

**context_manager.py** - Conversation memory
- **In-Memory Storage**: Deque with configurable max size
- **Persistent Storage**: JSON lines in `conversations/chat_{id}.txt`
- **Auto-Cleanup**: Removes conversations after 24 hours of inactivity
- **Context Loading**: Restores conversations on bot restart

### 6. **LLM Integration**

**model.py** - Ollama interface
- **Local LLM**: Ollama server (configurable model)
- **Context Injection**: Combines RAG context + conversation history
- **Prompt Engineering**: System prompt with document context

**Request Flow:**
```
User Query → RAG Context → Conversation History → System Prompt → Ollama → Response
```

### 7. **Additional Features**

**image_generator.py**
- Primary: Pollinations.ai API
- Fallback: PIL-based text image generation

**summary_generator.py**
- Chat history summarization
- Time-based log file analysis
- LLM-powered summary generation

**message_logger.py**
- Per-chat JSON logging in `logs/chat_{id}.json`
- Structured message storage with timestamps

**debug_logger.py**
- Error tracking in `logs/debug.log`
- Exception logging with stack traces

### 8. **Intent Router** (semantic routing layer)

**`intent_router.py`** is the single decision point for every incoming message. Before it existed, routing logic was scattered across four separate modules (`web_search.py`, `image_generator.py`, `summary_generator.py`, `main.py`), each doing its own keyword check independently. The router consolidates all of that into one place and adds genuine semantic understanding on top.

---

#### Core data structures

```python
class IntentType(Enum):
    NORMAL_CHAT           = "normal_chat"
    WEB_SEARCH_EXPLICIT   = "web_search_explicit"
    WEB_SEARCH_FRESHNESS  = "web_search_freshness"
    IMAGE_GENERATION      = "image_generation"
    SUMMARY_MEMORY        = "summary_memory"
    SUMMARY_FILE          = "summary_file"

@dataclass
class IntentResult:
    intent:     IntentType
    confidence: float         # 0.0–1.0
    query:      str | None    # cleaned search query (search intents only)
    explicit:   bool          # True = user explicitly asked for this action
    reason:     str | None    # one-sentence explanation (logged, not shown to user)
    source:     str           # "exact_trigger" | "semantic_classifier" | "fallback"
```

`IntentResult.source` lets you trace exactly why a given routing decision was made — useful when debugging unexpected behaviour in `logs/debug.log`.

---

#### Three-stage pipeline

Every call to `router.classify(text, history)` goes through the same three stages in order:

```
Stage 1 — Fast-path exact triggers
          ↓ (no match)
Stage 2 — Semantic LLM classifier
          ↓ (error / low confidence / router disabled)
Stage 3 — Fallback: NORMAL_CHAT
```

**Stage 1 — Fast-path (no LLM call)**

Checks configured and hardcoded triggers against the lowercased message text. Returns immediately at `confidence=1.0` if anything matches. Four trigger groups are checked in this order:

| Group | Source | Example trigger |
|---|---|---|
| Web search | `config.xml <triggers>` | `поиск в интернете` |
| Image generation | hardcoded in `intent_router.py` | `нарисуй`, `картинк*` |
| Memory summary | `config.xml <summary_triggers><memory>` | `бот, резюме` |
| File summary | `config.xml <summary_triggers><file>` | `бот, логи` |

Image keywords use prefix matching to handle Russian noun inflection:
```
"картинка" → also matches "картинку", "картинки", "картинке"
```
This is done by checking `word.startswith(kw[:max(4, len(kw)-2)])` across all words in the message.

For web-search triggers the trigger phrase is stripped from the text to produce a cleaner `query`:
```
"Товарищ Сталин, поиск в интернете курс рубля"
→ query = "Товарищ Сталин,  курс рубля"   (trigger removed)
```

**Stage 2 — Semantic classifier**

When no fast-path trigger matches, a single bare LLM call is made via `model.raw_llm_call()`. This function is completely separate from `model.modelResponse()` — it sends no RAG context, no persona system prompt, and uses `temperature=0` for deterministic output. It runs in a daemon thread and respects the configured timeout.

The classifier receives a compact prompt containing:
1. A description of all six intent types with Russian examples
2. The last `context_turns × 2` messages from conversation history (capped at 200 chars each) — this allows resolving pronouns like "посмотри тогда" when the subject was established earlier
3. The current message

It is instructed to return only this JSON:
```json
{
  "intent": "web_search_explicit",
  "confidence": 0.97,
  "query": "latest stable PostgreSQL version",
  "explicit": true,
  "reason": "User explicitly asks to look this up online"
}
```

The parser then:
- Strips markdown code fences (` ```json ... ``` `)
- Extracts the first `{...}` block with a regex
- Tries `json.loads()`, retries after stripping trailing commas if that fails
- Validates that `intent` is a known `IntentType` value
- Checks `confidence >= threshold` (default 0.70) — below threshold falls through to Stage 3
- Suppresses `WEB_SEARCH_FRESHNESS` if `smart_search_enabled=false` in config
- Falls back to original message text as `query` if the model returned `null`

Any exception — JSON parse failure, unknown intent value, Ollama timeout, connection error — is caught and leads to Stage 3.

**Stage 3 — Fallback**

Returns `IntentResult(intent=NORMAL_CHAT, source="fallback")`. The bot answers from RAG + conversation history as normal. The user sees no error; the reason is written to `logs/debug.log`.

---

#### Query rewriting

One practical benefit of the semantic path is that the LLM rewrites the user's message into a clean search query before it hits DuckDuckGo/Brave/Google. Addressing words, persona names, and conversational filler are stripped:

```
User:   "Товарищ Сталин, не могли бы вы разыскать в этих ваших
          интернетах сведения о запуске реактора ИТЭР?"
Query:  "ИТЭР реактор запуск"

User:   "можно узнать, что сейчас пишут о ценах на газ?"
Query:  "цены на газ текущие"
```

On the fast-path (exact trigger match) this rewriting only removes the trigger phrase itself. The semantic path produces a genuinely compressed query.

---

#### Two distinct web-search intents

The router distinguishes two reasons to run a web search, which behave differently:

**`WEB_SEARCH_EXPLICIT`** — the user said so in some form. Fires regardless of any config flag. Examples that all map here:
```
найди в интернете последние новости о PostgreSQL
посмотри в сети информацию об этом
погугли историю этого проекта
проверь в интернете, правда ли это
Товарищ Сталин, а не могли бы вы мне найти в Интернете вот это
разыщите-ка мне в этих ваших интернетах информацию о реакторах
не соблаговолите ли вы разыскать это во всемирной паутине?
глянь, что пишут об этом в сети
```
None of these contain the configured trigger phrases. They are classified purely by semantic meaning.

**`WEB_SEARCH_FRESHNESS`** — the user did not ask to search, but the answer requires current data. Only fires when `smart_search_enabled=true`. Examples:
```
кто сейчас премьер-министр Канады?    → needs current data
какая сейчас цена биткоина?           → real-time price
последняя стабильная версия PostgreSQL? → version changes
что произошло сегодня в Берлине?      → today's news
```
When `smart_search_enabled=false`, these fall back to `NORMAL_CHAT` and are answered from RAG/LLM knowledge only.

---

#### Conversation context for pronoun resolution

The router passes the last `context_turns` exchanges to the classifier. This handles cases like:

```
User: Расскажи о PostgreSQL 19.
Bot:  [answers from RAG]
User: Посмотри тогда в интернете.   ← "тогда" / "это" refers to the previous topic
```

Without history, "Посмотри тогда в интернете" is ambiguous. With 2 turns of context the classifier sees the prior subject and can produce `query = "PostgreSQL 19"`.

Only `context_turns × 2` messages are sent (default: last 4 messages), each truncated to 200 characters. Full conversation history is never sent to the classifier.

---

#### Routing decisions in the debug log

Every call to `classify()` appends one line to `logs/debug.log`:

```
INFO - IntentRouter: intent=web_search_explicit confidence=0.97 source=semantic_classifier explicit=True query='PostgreSQL 19 release date' reason='User explicitly asks to look this up online'
INFO - IntentRouter: intent=normal_chat confidence=1.00 source=exact_trigger explicit=False query=None reason=None
INFO - IntentRouter: intent=normal_chat confidence=0.00 source=fallback reason='classifier error: timed out after 15s'
```

Fields logged: `intent`, `confidence`, `source`, `explicit`, `query`, `reason`.

---

#### Integration with main.py

`main.py` calls `intent_router.classify()` once per eligible message and dispatches to a dedicated handler function:

```python
result = intent_router.classify(full_text, conversation_history)

if result.intent == IntentType.WEB_SEARCH_EXPLICIT:
    _handle_web_search(chat_id, message, full_text, result, history)
elif result.intent == IntentType.WEB_SEARCH_FRESHNESS:
    if web_searcher.smart_search_enabled:
        _handle_web_search(...)
    else:
        _handle_normal_chat(...)
elif result.intent == IntentType.IMAGE_GENERATION:
    _handle_image(...)
elif result.intent == IntentType.SUMMARY_FILE:
    _handle_summary_file(...)
elif result.intent == IntentType.SUMMARY_MEMORY:
    _handle_summary_memory(...)
else:  # NORMAL_CHAT
    _handle_normal_chat(...)
```

The search handlers use `result.query` (the rewritten query) rather than the raw message text.

---

#### Group chat bypass rule

In group chats the bot normally only responds when a message contains a configured bot trigger word (e.g. "Сталин,") or is a direct reply to the bot. Operational intent triggers — web search, image, summary — bypass this rule, exactly as they did before the router was introduced. This is implemented in `_is_eligible()` in `main.py` by running `_fast_path()` independently before the full classification.

---

#### Failure guarantees

`classify()` is designed to never raise an exception to its caller:

| Failure | Behaviour |
|---|---|
| Ollama timeout | Thread abandoned after `classifier_timeout` seconds → NORMAL_CHAT |
| Ollama connection refused | Exception caught → NORMAL_CHAT |
| Empty LLM response | No JSON found → NORMAL_CHAT |
| Malformed JSON | Trailing-comma retry, then → NORMAL_CHAT |
| Unknown intent string | ValueError caught → NORMAL_CHAT |
| Missing `confidence` field | Defaults to 0.0 → below threshold → NORMAL_CHAT |
| Missing `query` field | Falls back to original message text |
| `smart_search_enabled=false` | `WEB_SEARCH_FRESHNESS` suppressed → NORMAL_CHAT |
| `intent_router enabled=false` | Semantic path skipped, fast-path still runs |

---

#### Limitations

- **Multi-intent messages** — "нарисуй картинку того, что сейчас происходит в Берлине" contains both image generation and freshness search. The fast-path fires first and returns `IMAGE_GENERATION`. There is no multi-intent planner.
- **Fast-path query rewriting is shallow** — on an exact trigger match only the trigger phrase itself is removed. The semantic path produces a properly compressed query.
- **No embedding-based classifier** — intent classification uses the same LLM as chat, not a dedicated embedding classifier. A small dedicated model (e.g. a fine-tuned BERT) would be faster and more reliable, but adds a dependency.

### 9. **Configuration**

**config.xml** - Bot settings
- Trigger words
- Model parameters (temperature, context size)
- Embedding model selection
- Feature toggles (web search, hybrid retrieval, semantic ranking)

**security.xml** - Credentials
- Telegram bot token
- API keys (if needed)

## Data Flow

### Standard Query:
```
1. User sends message
2. Context Manager retrieves conversation history
3. RAG System searches relevant documents
4. Knowledge Graph provides entity relationships
5. Model combines all context and generates response
6. Response logged and context updated
7. Message saved to persistent storage
```

### Document Upload:
```
1. User uploads document (EPUB, TXT, etc.)
2. Document downloaded to temp file
3. Content extracted and analyzed
4. Knowledge Graph extracts entities/relationships
5. Vector embeddings created
6. Document indexed for future queries
7. LLM analyzes document with user's question
```

### Web Search:
```
1. User triggers web search
2. Multi-source search executed in parallel
3. Results ranked by semantic similarity
4. Top pages scraped for content
5. LLM analyzes search results
6. Response includes sources and links
```

## Technology Stack

- **Bot Framework**: pyTelegramBotAPI
- **LLM**: Ollama (local inference)
- **RAG Framework**: LlamaIndex
- **Embeddings**: HuggingFace Transformers / Sentence-Transformers
- **NLP**: spaCy (Russian language model)
- **Web Scraping**: BeautifulSoup4, Requests
- **Image Generation**: Pollinations.ai API, Pillow
- **Document Processing**: ebooklib (EPUB support)

## Directory Structure

```
spikerabot/
├── main.py                    # Entry point + Telegram handlers
├── intent_router.py           # Semantic Intent Router (NEW)
├── model.py                   # Ollama LLM interface
├── rag_embeddings.py          # RAG system
├── knowledge_graph.py         # Knowledge graph builder
├── web_search.py              # Multi-source search
├── context_manager.py         # Conversation memory
├── message_logger.py          # Chat logging
├── debug_logger.py            # Error logging
├── image_generator.py         # Image generation
├── summary_generator.py       # Chat summarization
├── config_loader.py           # XML config parser
├── security_loader.py         # Credentials loader
├── config.xml                 # Bot configuration
├── security.xml               # Credentials (gitignored)
├── requirements.txt           # Python dependencies
├── test_intent_router.py      # Intent router unit tests (54 tests)
├── stalin/                    # Document collection
├── storage/                   # Vector store & graphs
├── conversations/             # Persistent chat history
└── logs/                      # Message & debug logs
```

## Key Features

1. **Hybrid RAG**: Vector search + Knowledge graph fusion
2. **Persistent Memory**: Conversations saved across restarts
3. **Multi-Source Search**: Intelligent web search with semantic ranking
4. **Document Analysis**: Upload and query documents in real-time
5. **Knowledge Extraction**: Automatic entity and relationship mapping
6. **Context-Aware**: Maintains conversation history per chat
7. **Group Chat Support**: Trigger words and reply detection
8. **Image Generation**: AI-powered image creation
9. **Smart Summarization**: Chat history analysis

## Configuration Reference

All runtime behavior is controlled through `config.xml`. No code changes needed for most customization.

### Bot trigger words (group chats only)

In group chats the bot only responds when a message contains one of the trigger words, or when someone replies directly to the bot. Configure them here:

```xml
<trigger_words>
    <word>бот,</word>
    <word>Сталин,</word>
</trigger_words>
```

Add or remove `<word>` entries freely. In private chats trigger words are ignored — the bot always responds.

### System prompt / persona

```xml
<system_prompt>
    <content>Ты - товарищ Сталин. Отвечай как товарищ Сталин...</content>
</system_prompt>
```

This is the instruction injected at the top of every LLM request. Change it to give the bot a different persona, language, or set of rules.

### Model settings

```xml
<model_settings>
    <model_name>gemma4:31b</model_name>       <!-- any model installed in Ollama -->
    <temperature>1</temperature>              <!-- 0 = deterministic, 2 = very creative -->
    <context_history_size>10</context_history_size>  <!-- messages kept in RAM per chat -->
    <embedding_model>sentence-transformers/paraphrase-multilingual-mpnet-base-v2</embedding_model>
    <documents_path>stalin/</documents_path>  <!-- folder scanned for RAG documents -->
    <request_timeout>600</request_timeout>    <!-- seconds before Ollama call times out -->
    <hybrid_retrieval>true</hybrid_retrieval> <!-- true = RRF fusion, false = separate sections -->
</model_settings>
```

To switch models just change `<model_name>` to any model you have pulled locally (`ollama list`).

### Intent Router

Controls the semantic routing layer (`intent_router.py`). The router runs after Telegram eligibility is checked but before any subsystem is invoked.

```xml
<intent_router>
    <!-- false = use only fast-path keyword matching, no LLM classifier -->
    <enabled>true</enabled>
    <!-- Minimum confidence to accept a semantic classification (0.0–1.0) -->
    <!-- Below this threshold the router falls back to NORMAL_CHAT -->
    <confidence_threshold>0.70</confidence_threshold>
    <!-- Recent conversation turns passed to the classifier for pronoun resolution -->
    <!-- Example: "посмотри тогда" requires knowing what "тогда" refers to -->
    <context_turns>2</context_turns>
    <!-- Seconds before the classifier Ollama call is abandoned -->
    <classifier_timeout>15</classifier_timeout>
</intent_router>
```

**Key behaviour:**
- Exact configured triggers always fire first at confidence=1.0 regardless of the `enabled` flag.
- Setting `enabled=false` skips the LLM classifier but keeps all keyword triggers working.
- `WEB_SEARCH_FRESHNESS` (e.g. "какая цена биткоина?") is suppressed when `smart_search_enabled=false`.
- Any classifier error or timeout silently falls back to `NORMAL_CHAT` — the bot never crashes.
- All routing decisions are written to `logs/debug.log` with intent, confidence, source, and query.

### Web search triggers

Web search is activated when a message contains **any** of these exact phrases (case-insensitive):

```xml
<web_search>
    <triggers>
        <trigger>поиск в интернете</trigger>
        <trigger>найди в сети</trigger>
        <trigger>что в интернете</trigger>
    </triggers>
</web_search>
```

**Example**: "Сталин, поиск в интернете последние новости о ядерной энергетике"

Add any phrase as a new `<trigger>` line. Triggers work in both private and group chats (in groups they bypass the bot trigger word check).

#### Smart auto-search

When `smart_search_enabled` is `true` the bot also silently decides on its own whether a question needs a web lookup — without the user typing a trigger phrase. The LLM classifies the query first; if it decides a search is needed it runs one and includes the results as extra context.

```xml
<smart_search_enabled>true</smart_search_enabled>
<smart_search_links>5</smart_search_links>           <!-- pages scraped per query -->
<parallel_extraction_workers>3</parallel_extraction_workers>  <!-- concurrent scrapers -->
<semantic_ranking>true</semantic_ranking>            <!-- rank by meaning, not just keywords -->
```

#### Search sources

Sources are tried in priority order; if one returns no results the next is tried automatically:

```xml
<sources>
    <source enabled="true" priority="1">duckduckgo</source>
    <source enabled="true" priority="2">brave</source>
    <source enabled="true" priority="3">google</source>
</sources>
```

Disable a source with `enabled="false"` or change priority order by editing the numbers.

### Image generation triggers

Hardcoded in `image_generator.py` (not in config.xml). The bot generates an image when the message contains any of:

```
картинка  изображение  фото  рисунок  нарисуй  покажи
```

**Example**: "нарисуй красный трактор"

Images are fetched from Pollinations.ai; if that fails a simple PIL text image is generated as fallback.

### Summary triggers

Two kinds of summary are available:

**Memory summary** — summarizes what the bot remembers from the current conversation (RAM):

```xml
<summary_triggers>
    <memory>
        <trigger>бот, резюме</trigger>
        <trigger>бот, саммари</trigger>
        <trigger>бот, итог</trigger>
        <trigger>бот, кратко</trigger>
        <trigger>бот, что обсуждали</trigger>
        <trigger>бот, о чем говорили</trigger>
    </memory>
```

**File summary** — reads persisted log files and summarizes a longer history:

```xml
    <file>
        <trigger>бот, резюме файлов</trigger>
        <trigger>бот, логи</trigger>
        <trigger>бот, история чата</trigger>
    </file>
</summary_triggers>
```

Both support time filtering. Examples:
- "бот, резюме с 14:30" — summary from 14:30 today
- "бот, логи за последние 2 часа" — last 2 hours from log files

### Credentials

Stored in `security.xml` (gitignored). Minimum required:

```xml
<security>
    <bot_token>YOUR_TELEGRAM_BOT_TOKEN</bot_token>
</security>
```

### Logging

```xml
<logging>
    <directory>logs</directory>
    <max_file_size_mb>10</max_file_size_mb>
    <debug_log_file>debug.log</debug_log_file>
</logging>
```

- `logs/chat_<id>.json` — full message history per chat
- `logs/debug.log` — errors and stack traces
- `conversations/chat_<id>.txt` — lightweight persistent context loaded on bot restart

---

## Installation

```bash
pip install -r requirements.txt
python -m spacy download ru_core_news_sm
ollama pull <your-model>
```

## Running

```bash
ollama serve   # Start Ollama server first
python main.py
```
