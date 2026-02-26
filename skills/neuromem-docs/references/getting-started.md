# Getting Started with neuromem

> **Time**: ~10 minutes | **Python**: 3.12+ | **Docker**: 20.0+

## 1. Install

### From PyPI (recommended)

```bash
pip install neuromem        # core
pip install neuromem[all]   # all optional dependencies (recommended)
```

### From source (developers)

```bash
git clone https://github.com/MatrixDriver/neuromem
cd neuromem
pip install -e ".[dev]"
```

### Optional dependency groups

| Group | Command | Purpose |
|-------|---------|---------|
| Core | `pip install neuromem` | Base functionality |
| S3 | `pip install neuromem[s3]` | File upload to MinIO/S3 |
| PDF | `pip install neuromem[pdf]` | PDF text extraction |
| Word | `pip install neuromem[docx]` | Word document extraction |
| Dev | `pip install neuromem[dev]` | pytest, testing tools |
| All | `pip install neuromem[all]` | Everything above |

## 2. Start PostgreSQL

neuromem uses PostgreSQL + pgvector + pg_search as its storage backend.

```bash
# Using the provided Docker Compose (recommended)
docker compose -f docker-compose.yml up -d db

# Verify
docker compose -f docker-compose.yml ps db
# STATUS should be "healthy"
```

> **pg_search**: Provides BM25 keyword search fused with vector search (RRF). If pg_search is unavailable, the system automatically falls back to PostgreSQL's built-in tsvector full-text search.

## 3. Get API Keys

### Embedding Provider (required, pick one)

- **Local model** (no API key): `pip install sentence-transformers`
- **SiliconFlow** (recommended for Chinese+English): [siliconflow.cn](https://siliconflow.cn/)
- **OpenAI**: [platform.openai.com](https://platform.openai.com/)

### LLM Provider (required, for memory extraction + reflection)

- **OpenAI** or **DeepSeek**: [platform.deepseek.com](https://platform.deepseek.com/)

### MinIO/S3 (optional, for file storage only)

```bash
docker compose -f docker-compose.yml up -d minio
```

## 4. First Example

```python
import asyncio
from neuromem import NeuroMemory, SiliconFlowEmbedding, OpenAILLM

async def main():
    async with NeuroMemory(
        database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5432/neuromem",
        embedding=SiliconFlowEmbedding(api_key="your-siliconflow-key"),
        llm=OpenAILLM(api_key="your-llm-key", model="deepseek-chat"),
    ) as nm:
        # Store message -> auto-extract memories
        await nm.ingest(
            user_id="alice", role="user",
            content="I work at ABC Company as a software engineer",
        )
        print("Message added, memories auto-extracted")

        # Hybrid recall
        result = await nm.recall(user_id="alice", query="Where does Alice work?")
        for r in result["merged"]:
            print(f"  [{r['score']:.2f}] {r['content']}")

asyncio.run(main())
```

Run: `python demo.py`

## 5. Environment Variables

```bash
DATABASE_URL=postgresql+asyncpg://neuromem:neuromem@localhost:5432/neuromem
SILICONFLOW_API_KEY=sk-...
EMBEDDING_PROVIDER=siliconflow   # siliconflow | openai | sentence_transformer
EMBEDDING_DIMS=1024              # default 1024 (BAAI/bge-m3)
```

```python
import os
from neuromem import NeuroMemory, SiliconFlowEmbedding

nm = NeuroMemory(
    database_url=os.environ["DATABASE_URL"],
    embedding=SiliconFlowEmbedding(api_key=os.environ["SILICONFLOW_API_KEY"]),
)
```

## 6. Service Ports

| Service | Port | Purpose |
|---------|------|---------|
| PostgreSQL | 5432 | Database |
| MinIO API | 9000 | Object storage |
| MinIO Console | 9001 | MinIO web UI |

## 7. Common Issues

### Connection refused

```bash
docker compose -f docker-compose.yml ps db      # check status
docker compose -f docker-compose.yml restart db  # restart
docker compose -f docker-compose.yml logs db     # check logs
```

### "relation does not exist"

`nm.init()` auto-creates tables. Ensure you're using `async with` (which calls init automatically).

### Vector dimension mismatch

Switching embedding providers with existing tables causes dimension conflicts. Drop and recreate in dev:

```sql
DROP TABLE IF EXISTS embeddings CASCADE;
```

Then re-run `await nm.init()`.

### "Storage not configured"

File features require `storage=S3Storage(...)` in the constructor and MinIO running.
