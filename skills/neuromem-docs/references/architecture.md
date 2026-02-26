# neuromem Architecture

## Design Principles

1. **Framework, not service**: No backend server — `from neuromem import NeuroMemory` directly in your Python code
2. **Pluggable Providers**: Embedding, LLM, Storage via abstract interfaces
3. **Async-first**: Full async/await pipeline
4. **user_id isolation**: All queries scoped by user_id, framework-enforced
5. **Facade pattern**: Simple top-level API, complex logic in service layer

## System Architecture

```
┌──────────────────────────────────────────────┐
│  Your Agent Application                       │
│  nm = NeuroMemory(database_url=..., ...)      │
├──────────────────────────────────────────────┤
│  Facade Layer (neuromem/_core.py)          │
│  neuromem main class                       │
│  ├── nm.ingest() / nm.recall()                 │
│  ├── nm.kv          (KVFacade)                │
│  ├── nm.conversations (ConversationsFacade)   │
│  ├── nm.files       (FilesFacade)             │
│  └── nm.graph       (GraphFacade)             │
├──────────────────────────────────────────────┤
│  Service Layer (neuromem/services/)         │
│  SearchService | KVService | ConversationSvc  │
│  FileService | GraphService | GraphMemorySvc  │
│  MemoryExtractionService | ReflectionService  │
│  MemoryService | TemporalService              │
├──────────────────────────────────────────────┤
│  Provider Layer (neuromem/providers/)       │
│  EmbeddingProvider → SiliconFlow / OpenAI     │
│  LLMProvider → OpenAILLM (DeepSeek compat)    │
│  ObjectStorage → S3Storage (MinIO/AWS/OBS)    │
├──────────────────────────────────────────────┤
│  Data Layer                                   │
│  PostgreSQL + pgvector + pg_search            │
│  SQLAlchemy 2.0 async (asyncpg driver)        │
└──────────────────────────────────────────────┘
```

## Data Models

All models isolated by `user_id`. No `tenant_id`.

| Model | Table | Purpose |
|-------|-------|---------|
| Embedding | `embeddings` | Vector memories (content + pgvector + memory_type + metadata) |
| Conversation | `conversations` | Raw conversation messages |
| ConversationSession | `conversation_sessions` | Session metadata |
| KeyValue | `key_values` | KV storage (JSONB value) |
| GraphNode | `graph_nodes` | Graph nodes (NodeType enum) |
| GraphEdge | `graph_edges` | Graph edges (EdgeType enum) |
| EmotionProfile | `emotion_profiles` | User emotion profile |
| Document | `documents` | Document metadata |

## Core Data Flow

### ingest() flow

```
nm.ingest(role="user")
  ├── Store to conversations table
  ├── Background: generate embedding (asyncio.create_task)
  ├── auto_extract=True → Background: LLM extract facts/episodes/relations
  │    ├── Store to embeddings table (vectorized)
  │    └── graph_enabled=True → Store to graph_nodes/edges
  └── Every reflection_interval messages → Background: digest()
```

### recall() flow

```
recall(query)
  ├── Parallel fetch (asyncio.gather):
  │    ├── Vector search (pgvector cosine + BM25 RRF)
  │    ├── Graph recall (GraphMemoryService)
  │    ├── Temporal filter (TemporalService)
  │    └── User profile (KV)
  ├── Merge phase:
  │    ├── Graph triple coverage boost (both ends +0.5, single +0.2, cap 2.0)
  │    ├── Graph triples → merged (source="graph")
  │    └── Sort merged by score desc
  └── Return: vector_results, graph_results, graph_context, user_profile, merged
```

### digest() flow

```
digest()
  ├── Analyze memories added since last watermark
  ├── LLM generates behavior patterns + phase summaries
  ├── Update EmotionProfile
  └── Advance last_reflected_at watermark
```

## Scoring Formula

```
score = rrf_score x recency x importance x graph_boost

rrf_score   = 1/(k+rank_vector) + 1/(k+rank_bm25), k=60
recency     = e^(-t / (decay_rate x (1 + arousal x 0.5)))
importance  = metadata.importance / 10  (default 0.5)
graph_boost = min(1.0 + coverage, 2.0)
```

- **recency**: Exponential decay; high emotional arousal slows forgetting by 50% (Ebbinghaus + flashbulb memory)
- **importance**: LLM-assigned 1-10 score at extraction time
- **graph_boost**: Memories covered by graph triples get ranking boost

## Emotion Architecture (3 layers)

| Layer | Scope | Storage | Example |
|-------|-------|---------|---------|
| **Micro** | Per-event annotation | memory metadata (valence/arousal/label) | "Felt nervous during interview" |
| **Meso** | Recent state (1-2 weeks) | emotion_profiles.latest_state | "Under work pressure lately" |
| **Macro** | Long-term profile | emotion_profiles.* | "Prone to anxiety, excited about tech" |

Emotion directly affects retrieval: high arousal memories decay slower in the scoring formula.

## Provider System

All providers are ABCs injected via constructor:

```python
# Built-in providers
SiliconFlowEmbedding(api_key="...")    # BAAI/bge-m3, 1024d, Chinese+English
OpenAIEmbedding(api_key="...")         # text-embedding-3-small, 1536d
OpenAILLM(api_key="...", model="...")  # Compatible with OpenAI/DeepSeek/Moonshot
S3Storage(endpoint="...", ...)         # MinIO / AWS S3 / Huawei OBS

# Custom: implement the ABC
class MyEmbedding(EmbeddingProvider):
    @property
    def dims(self) -> int: return 768
    async def embed(self, text: str) -> list[float]: ...
```

## Single PostgreSQL Advantage

All data in one PostgreSQL instance enables:

- **Atomic transactions**: `delete_user_data()` across 8 tables in one transaction (GDPR)
- **Cross-type queries**: `entity_profile()` JOINs memories + graph + conversations
- **Fusion scoring**: Graph boost applied to vector results in-process
- **Simple ops**: One `pg_dump` backs up everything; one `create_all()` sets up all tables
