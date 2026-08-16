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
│   Message    │ │ Context  │ │   Message   │
│   Router     │ │ Manager  │ │   Logger    │
└──────┬───────┘ └────┬─────┘ └─────────────┘
       │              │
       │              ▼
       │      ┌──────────────┐
       │      │Conversations/│
       │      │  (Persistent)│
       │      └──────────────┘
       │
       ├─────────────┬─────────────┬──────────────┐
       ▼             ▼             ▼              ▼
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│   RAG    │  │   Web    │  │  Image   │  │ Summary  │
│ System   │  │  Search  │  │Generator │  │Generator │
└────┬─────┘  └────┬─────┘  └──────────┘  └──────────┘
     │             │
     ▼             ▼
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

### 8. **Configuration**

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
├── main.py                    # Entry point
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
