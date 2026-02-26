# neuromem API Reference

> **Version**: 0.6.6 | **Python**: 3.12+ | **Last updated**: 2026-02-25

## Initialization

### NeuroMemory(...)

```python
from neuromem import NeuroMemory, SiliconFlowEmbedding, OpenAILLM, S3Storage

nm = NeuroMemory(
    database_url: str,                    # Required: PostgreSQL connection string
    embedding: EmbeddingProvider,         # Required: embedding provider
    llm: LLMProvider,                     # Required: for extraction + reflection
    storage: ObjectStorage | None = None, # Optional: for file management
    auto_extract: bool = True,            # Auto-extract memories from messages
    graph_enabled: bool = False,          # Enable knowledge graph
    reflection_interval: int = 20,        # Auto-reflect every N user messages (0=disable)
    pool_size: int = 10,                  # DB connection pool size
    echo: bool = False,                   # SQL debug logging
    on_extraction: Callable = None,       # Extraction completion callback
    on_llm_call: Callable = None,         # LLM call callback (duration_ms, model, success, etc.)
    on_embedding_call: Callable = None,   # Embedding call callback (text_count, duration_ms, etc.)
    extraction: ExtractionStrategy = None,# Custom extraction trigger strategy
)
```

**Lifecycle**: Use `async with` for automatic init/close:

```python
async with NeuroMemory(database_url="...", embedding=..., llm=...) as nm:
    # nm.init() called automatically
    ...
# nm.close() called automatically
```

### Dynamic Configuration

These settings can be changed at runtime:

```python
nm.reflection_interval = 10
nm.auto_extract = False
nm.graph_enabled = True
nm.on_extraction = my_callback
nm.on_llm_call = my_llm_callback
nm.on_embedding_call = my_embedding_callback
```

---

## Core API

### ingest()

Store a conversation message. With `auto_extract=True` (default), automatically extracts memories.

```python
msg = await nm.ingest(
    user_id: str,              # User ID
    role: str,                 # "user" or "assistant"
    content: str,              # Message content
    session_id: str | None = None,  # Auto-creates session if None
    metadata: dict | None = None,
) -> ConversationMessage       # Has: id, session_id, role, content, created_at
```

**Shortcut**: `nm.ingest()` is equivalent to `nm.conversations.ingest()`.

**Typical agent loop**:

```python
# 1. Store user message (auto-extracts memories)
await nm.ingest(user_id="alice", role="user", content="I work at Google")

# 2. Recall relevant memories
result = await nm.recall(user_id="alice", query="work", limit=5)

# 3. Generate reply with your LLM using recalled context
reply = your_llm.generate(context=result["merged"], ...)

# 4. Store assistant reply
await nm.ingest(user_id="alice", role="assistant", content=reply)
```

### recall()

Hybrid retrieval: RRF(vector + BM25) x recency x importance x graph_boost.

```python
result = await nm.recall(
    user_id: str,
    query: str,
    limit: int = 20,
    decay_rate: float | None = None,       # Time decay in seconds (default: 30 days)
    include_conversations: bool = False,    # Include raw conversation snippets in merged
    memory_type: str | None = None,        # Filter: "fact", "episodic", "insight", "general"
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    event_after: datetime | None = None,   # Filter by event timestamp
    event_before: datetime | None = None,
    as_of: datetime | None = None,         # Time-travel: recall memories as of a past point
) -> dict
```

**Return structure**:

```python
{
    "vector_results": [          # Extracted memories, scored
        {
            "id": "uuid",
            "content": "Works at Google",
            "memory_type": "fact",      # fact / episodic / insight / general
            "metadata": {
                "importance": 8,        # 1-10
                "emotion": {"valence": 0.6, "arousal": 0.4, "label": "satisfied"}
            },
            "score": 0.646,
        }, ...
    ],
    "conversation_results": [...],  # Raw conversation snippets (if include_conversations=True)
    "graph_results": [              # Knowledge graph triples
        {"subject": "alice", "relation": "WORKS_AT", "object": "google", "content": "..."}, ...
    ],
    "graph_context": ["alice -> WORKS_AT -> google", ...],  # Text for prompt injection
    "user_profile": {...},          # From KV profile namespace
    "merged": [                     # All sources merged, sorted by score desc
        {"content": "...", "source": "vector", "score": 0.646, ...},
        {"content": "alice -> WORKS_AT -> google", "source": "graph", ...},
    ]
}
```

**Scoring formula**:

```
score = rrf_score x recency x importance x graph_boost

rrf_score   = RRF(vector_similarity, bm25_score)  # 0-1
recency     = e^(-t / (decay_rate x (1 + arousal x 0.5)))  # 0-1, high arousal = slower decay
importance  = metadata.importance / 10  # 0.1-1.0, default 0.5
graph_boost = min(1.0 + coverage, 2.0)  # both ends +0.5, single end +0.2
```

### digest()

Generate insights and update emotion profile from recent memories.

```python
result = await nm.digest(
    user_id: str,
    batch_size: int = 50,      # Number of recent memories to analyze per LLM call
    background: bool = False,  # If True, runs as asyncio.create_task and returns None
) -> dict | None
```

**Return**:

```python
{
    "insights_generated": 2,
    "insights": [
        {"content": "User is a tech professional focused on backend", "category": "pattern"},
        {"content": "User under work pressure recently", "category": "summary"},
    ],
    "emotion_profile": {"latest_state": "...", "valence_avg": -0.3, ...},
}
```

### on_extraction callback

```python
def on_extraction(stats: dict):
    # stats keys: user_id, session_id, duration, facts_extracted,
    #             episodes_extracted, triples_extracted, messages_processed
    print(f"Extracted in {stats['duration']}s: {stats['facts_extracted']} facts")

nm = NeuroMemory(..., on_extraction=on_extraction)  # supports sync and async
```

### on_llm_call / on_embedding_call callbacks

```python
def on_llm_call(stats: dict):
    # stats keys: duration_ms, model, max_tokens, temperature, success
    print(f"LLM call: {stats['model']} in {stats['duration_ms']}ms")

def on_embedding_call(stats: dict):
    # stats keys: text_count, duration_ms, model, success
    print(f"Embedded {stats['text_count']} texts in {stats['duration_ms']}ms")

nm = NeuroMemory(..., on_llm_call=on_llm_call, on_embedding_call=on_embedding_call)
```

---

## Additional Methods

```python
# Time-travel: rollback memories to a past point
await nm.rollback_memories(user_id, to_time=some_datetime)

# Query memories by time range
mems = await nm.get_memories_by_time_range(user_id, start_time, end_time, memory_type=None, limit=50)

# Get recent memories (shortcut)
mems = await nm.get_recent_memories(user_id, days=7, memory_types=None, limit=50)

# Retry failed extractions
await nm.retry_failed_extractions(user_id, max_retries=3)

# Clear embedding cache
nm.clear_embedding_cache()
```

---

## KV Storage

Key-value storage for user preferences, configuration, etc.

```python
await nm.kv.set(user_id, namespace, key, value)        # value: str/int/float/bool/dict/list/None
value = await nm.kv.get(user_id, namespace, key)        # -> Any | None
items = await nm.kv.list(user_id, namespace, prefix="") # -> [{"key": ..., "value": ...}]
ok = await nm.kv.delete(user_id, namespace, key)         # -> bool
await nm.kv.batch_set(user_id, namespace, {"k1": v1, "k2": v2})
```

---

## Conversation Management

```python
# Batch add messages
session_id, msg_ids = await nm.conversations.add_messages_batch(
    user_id, messages=[{"role": "user", "content": "..."}], session_id=None
)

# Get session messages
msgs = await nm.conversations.get_session_messages(user_id, session_id, limit=100, offset=0)

# Get unextracted messages
msgs = await nm.conversations.get_unextracted_messages(user_id, session_id=None, limit=100)

# Close session
await nm.conversations.close_session(user_id, session_id)

# List sessions
sessions = await nm.conversations.list_sessions(user_id, limit=10)
# -> [ConversationSession with: session_id, message_count, created_at, updated_at]
```

---

## File Management

Requires `storage=S3Storage(...)` in constructor.

```python
# Upload file (auto-extracts text + generates embedding)
doc = await nm.files.upload(
    user_id, filename="report.pdf", file_data=bytes_data,
    category="work", tags=["quarterly"], metadata={}
)
# Supported: .txt, .md, .json, .csv, .pdf (needs [pdf]), .docx (needs [docx]), images (store only)

# Create from text (no S3 upload)
doc = await nm.files.create_from_text(user_id, title="Notes", content="...", category="work")

# List / Get / Delete
docs = await nm.files.list(user_id, category=None, tags=None, file_types=None, limit=50)
doc = await nm.files.get(user_id, file_id)
ok = await nm.files.delete(user_id, file_id)

# Vector search file content
results = await nm.files.search(user_id, query="...", limit=5, file_types=None, category=None)
```

---

## Knowledge Graph

Requires `graph_enabled=True` in constructor. Based on PostgreSQL relational tables (no Apache AGE).

```python
from neuromem.models.graph import NodeType, EdgeType

# NodeType: USER, MEMORY, CONCEPT, ENTITY, PERSON, ORGANIZATION, LOCATION, EVENT, SKILL
# EdgeType: HAS_MEMORY, MENTIONS, RELATED_TO, KNOWS, ABOUT,
#           WORKS_AT, LIVES_IN, HAS_SKILL, STUDIED_AT, BELONGS_TO, USES,
#           MET, ATTENDED, VISITED, OCCURRED_AT, OCCURRED_ON,
#           HOBBY, OWNS, LOCATED_IN, BORN_IN, SPEAKS, COLLEAGUE, CUSTOM

# Create nodes and edges
await nm.graph.create_node(NodeType.USER, "alice", properties={"name": "Alice"})
await nm.graph.create_edge(
    NodeType.USER, "alice", EdgeType.WORKS_AT,
    NodeType.ENTITY, "google", properties={"since": "2023"}
)

# Query
node = await nm.graph.get_node(user_id, NodeType.USER, "alice")
neighbors = await nm.graph.get_neighbors(
    user_id, NodeType.USER, "alice",
    edge_types=[EdgeType.WORKS_AT], direction="both", limit=10
)
paths = await nm.graph.find_path(
    NodeType.USER, "alice", NodeType.ENTITY, "google", max_depth=3
)

# Update / Delete
await nm.graph.update_node(NodeType.USER, "alice", properties={"age": 31})
await nm.graph.delete_node(NodeType.USER, "alice")
```

---

## Data Lifecycle

```python
# Delete ALL user data atomically (GDPR compliance)
result = await nm.delete_user_data(user_id)
# -> {"deleted": {"embeddings": 15, "graph_edges": 3, ...}}

# Export all user data
data = await nm.export_user_data(user_id)
# -> {"memories": [...], "conversations": [...], "graph": {...}, "kv": [...], "profile": ..., "documents": [...]}
```

## Analytics

```python
# Memory statistics
stats = await nm.stats(user_id)
# -> {"total": 42, "by_type": {"fact": 20, ...}, "by_week": [...], "active_entities": 12, "profile_summary": ...}

# Cold (unaccessed) memories
cold = await nm.cold_memories(user_id, threshold_days=90, limit=50)
# -> [{"id": ..., "content": ..., "access_count": 0, "last_accessed_at": None, ...}]

# Entity profile (cross-type)
profile = await nm.entity_profile(user_id, entity="Google")
# -> {"entity": ..., "facts": [...], "graph_relations": [...], "conversations": [...], "timeline": [...]}
```

---

## Provider Interfaces

### EmbeddingProvider (ABC)

```python
from neuromem.providers.embedding import EmbeddingProvider

class CustomEmbedding(EmbeddingProvider):
    @property
    def dims(self) -> int: return 1024
    async def embed(self, text: str) -> list[float]: ...
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
```

Built-in: `SiliconFlowEmbedding` (BAAI/bge-m3, 1024d), `OpenAIEmbedding` (text-embedding-3-small, 1536d)

### LLMProvider (ABC)

```python
from neuromem.providers.llm import LLMProvider

class CustomLLM(LLMProvider):
    async def chat(self, messages: list[dict], **kwargs) -> str: ...
```

Built-in: `OpenAILLM` (compatible with OpenAI, DeepSeek, Moonshot)

### ObjectStorage (ABC)

```python
from neuromem.storage.base import ObjectStorage

class CustomStorage(ObjectStorage):
    async def upload(self, key: str, data: bytes) -> str: ...
    async def download(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> bool: ...
    async def exists(self, key: str) -> bool: ...
```

Built-in: `S3Storage` (MinIO / AWS S3 / Huawei OBS)
