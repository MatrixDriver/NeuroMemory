---
name: neuromem-docs
description: Documentation for neuromem - a Python memory framework for AI agents. Use when building agents that need memory storage, retrieval, and reasoning with neuromem.
---

# neuromem Documentation

neuromem is a **Python memory framework** for AI agent developers. It provides memory storage, retrieval, and reasoning capabilities — `from neuromem import NeuroMemory` in your agent code, no server deployment needed. Published on PyPI.

## Core Operations

neuromem revolves around three operations:

| Operation | Method | Purpose |
|-----------|--------|---------|
| **Store** | `ingest()` | Store conversation messages + auto-extract memories (facts, episodes, relations, user profile) |
| **Recall** | `recall()` | Hybrid retrieval: vector + BM25 + graph fusion scoring |
| **Digest** | `digest()` | Generate insights + update emotion profile |

## Quick Reference

### Initialization

```python
from neuromem import NeuroMemory, SiliconFlowEmbedding, OpenAILLM

async with NeuroMemory(
    database_url="postgresql+asyncpg://user:pass@host:5432/db",
    embedding=SiliconFlowEmbedding(api_key="..."),
    llm=OpenAILLM(api_key="...", model="deepseek-chat"),
    auto_extract=True,       # default: auto-extract memories from messages
    graph_enabled=False,     # enable knowledge graph storage
    reflection_interval=20,  # auto-digest every N user messages (0=disable)
) as nm:
    ...
```

### ingest()

```python
msg = await nm.ingest(
    user_id="alice",
    role="user",          # "user" or "assistant"
    content="I work at Google as a backend engineer",
    session_id=None,      # auto-creates new session if None
)
# -> auto-extracts: fact "works at Google", fact "backend engineer"
```

### recall()

```python
result = await nm.recall(
    user_id="alice",
    query="Where does Alice work?",
    limit=20,
    memory_type=None,           # filter: "fact", "episodic", "insight", "general"
    created_after=None,         # datetime filter
    as_of=None,                 # time-travel: recall as of a past point
)
# Returns: { "vector_results": [...], "graph_results": [...],
#            "graph_context": [...], "user_profile": {...}, "merged": [...] }

# Use merged results (recommended)
for mem in result["merged"]:
    print(f"[{mem['source']}] {mem['content']} (score: {mem['score']:.2f})")
```

### digest()

```python
result = await nm.digest(user_id="alice", batch_size=50, background=False)
# Returns: { "insights_generated": 2, "insights": [...], "emotion_profile": {...} }
# background=True → runs as asyncio.create_task, returns None
```

## Memory Types

| Type | Storage | Retrieval | Example |
|------|---------|-----------|---------|
| **Fact** | Embedding + Graph | `recall()` | "Works at Google" |
| **Episode** | Embedding | `recall()` | "Had interview yesterday, felt nervous" |
| **Relation** | Graph (relational tables) | `graph.get_neighbors()` | `(alice)-[WORKS_AT]->(google)` |
| **Insight** | Embedding | `recall()` | "User tends to work at night" |
| **Emotion Profile** | Table | `digest()` auto-updates | "Prone to anxiety, excited about tech" |
| **Preference** | KV (profile namespace) | `kv.get()` | `["likes coffee", "prefers dark mode"]` |
| **General** | Embedding | `recall()` | General-purpose memory |

## Sub-Facades

| Facade | Access | Purpose |
|--------|--------|---------|
| `nm.kv` | KV storage | `set()`, `get()`, `list()`, `delete()`, `batch_set()` |
| `nm.conversations` | Conversation management | `ingest()`, `get_session_messages()`, `list_sessions()` |
| `nm.files` | File management (needs S3Storage) | `upload()`, `list()`, `search()`, `delete()` |
| `nm.graph` | Knowledge graph (needs `graph_enabled=True`) | `create_node()`, `create_edge()`, `get_neighbors()`, `find_path()` |

## Documentation

For detailed information, see the reference docs in this skill:

- **[API Reference](references/api.md)** — Complete API signatures, parameters, return types, and examples
- **[Getting Started](references/getting-started.md)** — Installation, configuration, first working example
- **[Architecture](references/architecture.md)** — Data models, data flow, Provider system, scoring formula

## Discovering neuromem in a Project

```bash
# Check if neuromem is used
Glob: "**/requirements*.txt" or "**/pyproject.toml"  # look for "neuromem"
Grep: "from neuromem" or "import neuromem"

# Find configuration
Grep: "neuromem(" --type py
Grep: "database_url.*postgresql" --type py
```

## Key Concepts

- **Providers**: Embedding, LLM, and Storage are pluggable ABCs injected via constructor
- **user_id isolation**: All queries are scoped by `user_id` — framework-enforced
- **Async-first**: All APIs are `async def`, use `async with` for lifecycle management
- **Single PostgreSQL**: All data (vectors, graph, conversations, KV, documents) in one PostgreSQL — atomic transactions, no multi-DB coordination
- **Background tasks**: Embedding generation, memory extraction, and reflection run as `asyncio.create_task()` in the background
- **Observability callbacks**: `on_extraction`, `on_llm_call`, `on_embedding_call` for monitoring performance
- **Time-travel**: `recall(as_of=...)` and `rollback_memories()` for point-in-time queries
