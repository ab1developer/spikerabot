# Semantic Search Ranking

## Overview
Semantic ranking uses sentence embeddings to calculate similarity between search queries and results, providing more accurate relevance scores than keyword matching.

## How It Works

### Semantic Mode (semantic_ranking=true)
- **70%** Semantic similarity (cosine similarity of embeddings)
- **20%** Domain authority (trusted sources)
- **10%** Recency bonus (current year mentions)

### Keyword Mode (semantic_ranking=false)
- **40%** Title keyword matching
- **30%** Snippet keyword matching
- **20%** Domain authority
- **10%** Recency bonus

## Benefits

### Better for Russian Language
LaBSE (Language-agnostic BERT Sentence Embedding) understands:
- Synonyms: "искусственный интеллект" ≈ "ИИ" ≈ "AI"
- Context: "современные технологии" matches "новые разработки"
- Cross-lingual: Russian query matches English results

### More Accurate
- Understands semantic meaning, not just keywords
- Handles typos and variations better
- Cross-language matching (Russian ↔ English)

## Configuration

In `config.xml`:
```xml
<semantic_ranking>true</semantic_ranking>
```

Set to `false` to use keyword-based ranking (faster, less accurate).

## Performance

- **Semantic**: ~50ms per result (embedding calculation)
- **Keyword**: ~1ms per result (string matching)

For 5 results: ~250ms overhead (acceptable for better accuracy)

## Model

Uses the same embedding model as RAG:
- **Model**: sentence-transformers/LaBSE
- **Dimension**: 768
- **Languages**: 109+ languages including Russian

## Example

**Query**: "биография Сталина"

**Result 1**: "Иосиф Сталин - биография советского лидера"
- Semantic score: 88.92/100 ✓ High relevance

**Result 2**: "История СССР"
- Semantic score: 45.23/100 ✗ Lower relevance

Semantic ranking correctly identifies Result 1 as more relevant despite both containing related keywords.
