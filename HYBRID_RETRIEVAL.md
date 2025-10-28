# Hybrid Retrieval (Vector + Knowledge Graph)

## Overview
Hybrid retrieval merges results from vector search and knowledge graph using Reciprocal Rank Fusion (RRF) for better context quality.

## How It Works

### Traditional Approach (hybrid_retrieval=false)
```
Query → Vector Search → Results A
     → KG Search → Results B
     → Concatenate: "Vector: A\n\nKG: B"
```

**Problem**: Results shown separately, no ranking between sources

### Hybrid Approach (hybrid_retrieval=true) ✅
```
Query → Vector Search → Results A (ranked 1-6)
     → KG Search → Results B (ranked 1-6)
     → RRF Fusion → Merged & Re-ranked (top 3)
     → Unified Context
```

**Benefit**: Best results from both sources, intelligently merged

## Reciprocal Rank Fusion (RRF)

### Algorithm
For each result at rank `r` from source `s`:
```
score = 1 / (k + r)
```
where `k = 60` (constant)

### Example
**Vector Results**:
1. "Stalin born in Gori" → score = 1/(60+1) = 0.0164
2. "Stalin led USSR" → score = 1/(60+2) = 0.0161

**KG Results**:
1. "Stalin → born_in → Gori" → score = 1/(60+1) = 0.0164
2. "Gori → located_in → Georgia" → score = 1/(60+2) = 0.0161

**Merged** (if same content):
- "Stalin born in Gori" → 0.0164 + 0.0164 = 0.0328 ✅ Top result!

## Configuration

In `config.xml`:
```xml
<hybrid_retrieval>true</hybrid_retrieval>
```

- `true`: RRF fusion (recommended)
- `false`: Separate vector + KG sections

## Benefits

### 1. Better Ranking
- Combines semantic similarity (vector) with structured knowledge (graph)
- Results appearing in both sources get boosted

### 2. Diverse Results
- Prevents one source from dominating
- Balances factual (KG) and contextual (vector) information

### 3. Deduplication
- Same information from both sources merged automatically
- Reduces redundancy

## Implementation Details

### Code Flow
```python
def get_relevant_context(query, top_k=3):
    # 1. Get vector results (top_k * 2)
    vector_nodes = vector_search(query, top_k=6)
    
    # 2. Get KG results
    kg_response = kg_search(query)
    kg_chunks = split_into_sentences(kg_response)
    
    # 3. Apply RRF
    fused = reciprocal_rank_fusion(vector_nodes, kg_chunks)
    
    # 4. Return top_k merged results
    return build_context(fused[:top_k])
```

### Result Format
```
[Vector] Stalin was born in Gori, Georgia in 1878...

[KG] Stalin → born_in → Gori. Gori → located_in → Georgia

[Vector] Stalin became General Secretary in 1922...
```

## Performance

**Before** (Separate):
- Vector: 3 results
- KG: 1 response
- Total: 4 items (may have duplicates)

**After** (Hybrid):
- Merged: 3 best results from both sources
- Deduplicated automatically
- Better relevance

## Use Cases

### When Hybrid Helps
- ✅ Factual questions: "Where was Stalin born?"
  - Vector: contextual passages
  - KG: structured facts (Stalin → born_in → Gori)
  - Hybrid: Best of both!

- ✅ Relationship queries: "Who influenced Stalin?"
  - Vector: biographical text
  - KG: relationship triplets
  - Hybrid: Complete picture

### When to Disable
- ❌ Pure semantic search (no structured data)
- ❌ Debugging (want to see sources separately)

## Testing

Test hybrid retrieval:
```python
from rag_embeddings import RAGEmbeddings

rag = RAGEmbeddings()
context = rag.get_relevant_context("Where was Stalin born?", top_k=3)
print(context)
```

Expected output: Mix of `[Vector]` and `[KG]` tagged results

## Summary

**Hybrid Retrieval** = Vector Search + Knowledge Graph + RRF Fusion

- ✅ Better ranking
- ✅ Deduplication
- ✅ Balanced results
- ✅ Configurable

Set `hybrid_retrieval=true` in config.xml to enable!
