# NeuroMemory Python SDK

Official Python SDK for NeuroMemory - Memory-as-a-Service for AI Agents.

## Installation

```bash
# From source (development)
pip install -e /path/to/NeuroMemory/sdk

# Or using uv (recommended)
uv pip install -e /path/to/NeuroMemory/sdk
```

## Quick Start

```python
from neuromemory_client import NeuroMemoryClient

# Initialize the client
client = NeuroMemoryClient(
    api_key="nm_your_api_key_here",
    base_url="http://localhost:8765"  # Or your deployed URL
)

# Store user preferences
client.preferences.set(
    user_id="user123",
    key="language",
    value="zh-CN"
)

# Retrieve preferences
pref = client.preferences.get(user_id="user123", key="language")
print(f"Language: {pref['value']}")  # Output: Language: zh-CN

# Add memories for semantic search
client.add_memory(
    user_id="user123",
    content="I work at ABC Company as a software engineer"
)

# Search memories
results = client.search(
    user_id="user123",
    query="where does user work",
    limit=5
)
for result in results:
    print(f"Score: {result['score']:.3f} - {result['content']}")
```

## Features

### 1. Preference Management

Preferences are simple key-value pairs for storing user settings and metadata.

```python
# Set a preference (upsert: creates or updates)
client.preferences.set(
    user_id="user123",
    key="theme",
    value="dark",
    metadata={"source": "user_settings"}  # Optional metadata
)

# Get a specific preference
pref = client.preferences.get(user_id="user123", key="theme")
# Returns: {"key": "theme", "value": "dark", "metadata": {...}, ...}

# List all preferences for a user
prefs = client.preferences.list(user_id="user123")
for pref in prefs:
    print(f"{pref['key']}: {pref['value']}")

# Delete a preference
client.preferences.delete(user_id="user123", key="theme")
```

### 2. Semantic Memory Search

Store and search user memories using semantic embeddings.

```python
# Add a memory
client.add_memory(
    user_id="user123",
    content="My favorite color is blue",
    metadata={"type": "preference", "category": "personal"}
)

# Search with natural language
results = client.search(
    user_id="user123",
    query="what color does the user like",
    limit=3,
    min_score=0.5  # Optional: filter by similarity score
)

for result in results:
    print(f"Content: {result['content']}")
    print(f"Score: {result['score']}")
    print(f"Metadata: {result.get('metadata', {})}")
    print("---")
```

### 3. User Memory Overview

Get a summary of all memories for a user.

```python
overview = client.get_user_memories(user_id="user123")
print(f"Total memories: {overview['embedding_count']}")
print(f"Total preferences: {overview['preference_count']}")
```

## API Reference

### NeuroMemoryClient

Main client class for interacting with NeuroMemory API.

**Constructor:**
```python
NeuroMemoryClient(api_key: str, base_url: str = "http://localhost:8765")
```

**Parameters:**
- `api_key` (str): Your NeuroMemory API key (starts with `nm_`)
- `base_url` (str): Base URL of the NeuroMemory API server

**Sub-clients:**
- `preferences`: PreferencesClient - Manage user preferences
- `search`: SearchClient - Search memories
- Direct methods: `add_memory()`, `search()`, `get_user_memories()`

### PreferencesClient

**Methods:**

#### `set(user_id: str, key: str, value: str, metadata: dict = None) -> dict`

Set or update a preference.

**Parameters:**
- `user_id`: Unique identifier for the user
- `key`: Preference key
- `value`: Preference value
- `metadata`: Optional metadata dictionary

**Returns:** Preference object

#### `get(user_id: str, key: str) -> dict | None`

Get a specific preference.

**Returns:** Preference object or None if not found

#### `list(user_id: str) -> list[dict]`

List all preferences for a user.

**Returns:** List of preference objects

#### `delete(user_id: str, key: str) -> bool`

Delete a preference.

**Returns:** True if deleted, False if not found

### SearchClient

**Methods:**

#### `add_memory(user_id: str, content: str, metadata: dict = None) -> dict`

Add a memory for semantic search.

**Parameters:**
- `user_id`: Unique identifier for the user
- `content`: Memory content (text)
- `metadata`: Optional metadata dictionary

**Returns:** Memory object with embedding

#### `search(user_id: str, query: str, limit: int = 10, min_score: float = 0.0) -> list[dict]`

Search memories using semantic similarity.

**Parameters:**
- `user_id`: Unique identifier for the user
- `query`: Search query (natural language)
- `limit`: Maximum number of results (default: 10)
- `min_score`: Minimum similarity score 0.0-1.0 (default: 0.0)

**Returns:** List of memory objects with scores

## Error Handling

The SDK raises `httpx.HTTPStatusError` for API errors:

```python
from httpx import HTTPStatusError

try:
    client.preferences.set(user_id="user123", key="lang", value="en")
except HTTPStatusError as e:
    print(f"API Error: {e.response.status_code}")
    print(f"Detail: {e.response.json().get('detail')}")
```

Common status codes:
- `401`: Invalid API key
- `404`: Resource not found
- `409`: Conflict (e.g., duplicate email)
- `500`: Server error

## Best Practices

### 1. User ID Management

Use consistent, unique identifiers for users:

```python
# Good: Use stable identifiers
user_id = f"user_{database_user_id}"
user_id = "user@example.com"

# Avoid: Session-based or temporary IDs
user_id = session.id  # Changes per session
```

### 2. Preference Keys

Use namespaced keys for better organization:

```python
# Good: Namespaced keys
client.preferences.set(user_id=uid, key="ui.theme", value="dark")
client.preferences.set(user_id=uid, key="notification.email", value="true")

# Avoid: Flat keys
client.preferences.set(user_id=uid, key="theme", value="dark")
```

### 3. Memory Content

Write clear, contextual memory content:

```python
# Good: Clear context
client.add_memory(uid, "User prefers meetings scheduled in the morning")

# Avoid: Ambiguous content
client.add_memory(uid, "morning")  # Too vague
```

### 4. Metadata Usage

Use metadata for filtering and categorization:

```python
client.add_memory(
    user_id=uid,
    content="Completed Python course on 2024-01-15",
    metadata={
        "type": "achievement",
        "category": "education",
        "date": "2024-01-15"
    }
)
```

## Examples

### Chat Bot with Memory

```python
from neuromemory_client import NeuroMemoryClient

client = NeuroMemoryClient(api_key="nm_xxx")

def chat(user_id: str, user_message: str) -> str:
    # Search relevant memories
    memories = client.search(
        user_id=user_id,
        query=user_message,
        limit=3,
        min_score=0.6
    )

    # Build context from memories
    context = "\n".join([m['content'] for m in memories])

    # Generate response with context (pseudo-code)
    response = llm.generate(
        prompt=f"Context:\n{context}\n\nUser: {user_message}\nAssistant:"
    )

    # Store conversation as memory
    client.add_memory(
        user_id=user_id,
        content=f"User said: {user_message}. I replied: {response}",
        metadata={"type": "conversation"}
    )

    return response
```

### User Settings Manager

```python
class UserSettings:
    def __init__(self, client: NeuroMemoryClient, user_id: str):
        self.client = client
        self.user_id = user_id

    def get_theme(self) -> str:
        pref = self.client.preferences.get(self.user_id, "ui.theme")
        return pref['value'] if pref else "light"

    def set_theme(self, theme: str):
        self.client.preferences.set(self.user_id, "ui.theme", theme)

    def get_all_settings(self) -> dict:
        prefs = self.client.preferences.list(self.user_id)
        return {p['key']: p['value'] for p in prefs}
```

## Development

### Running Tests

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest tests/

# Run with coverage
pytest --cov=neuromemory_client tests/
```

### Type Checking

```bash
mypy sdk/neuromemory_client
```

## License

[Your License Here]

## Support

- Documentation: [Link to docs]
- Issues: [GitHub Issues]
- Email: support@example.com
