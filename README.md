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

## Installation

```bash
pip install -r requirements.txt
python -m spacy download ru_core_news_sm
ollama pull <your-model>
```

## Running

```bash
ollama serve  # Start Ollama server
python main.py
``` 
