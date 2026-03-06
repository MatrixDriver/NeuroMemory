"""Sub-facades for NeuroMemory: KV, Files, Graph.

These lightweight wrappers provide session-per-call isolation
and delegate all logic to the underlying Service layer.
"""

from __future__ import annotations

from typing import Any

from neuromem.db import Database
from neuromem.providers.embedding import EmbeddingProvider
from neuromem.storage.base import ObjectStorage


class KVFacade:
    """Key-value storage facade.

    user_id is used as scope_id internally to enforce user isolation.
    """

    def __init__(self, db: Database):
        self._db = db

    async def set(self, user_id: str, namespace: str, key: str, value):
        from neuromem.services.kv import KVService
        async with self._db.session() as session:
            svc = KVService(session)
            return await svc.set(namespace, user_id, key, value)

    async def get(self, user_id: str, namespace: str, key: str):
        from neuromem.services.kv import KVService
        async with self._db.session() as session:
            svc = KVService(session)
            return await svc.get(namespace, user_id, key)

    async def list(self, user_id: str, namespace: str, prefix: str | None = None, limit: int = 100):
        from neuromem.services.kv import KVService
        async with self._db.session() as session:
            svc = KVService(session)
            return await svc.list(namespace, user_id, prefix, limit)

    async def delete(self, user_id: str, namespace: str, key: str) -> bool:
        from neuromem.services.kv import KVService
        async with self._db.session() as session:
            svc = KVService(session)
            return await svc.delete(namespace, user_id, key)

    async def batch_set(self, user_id: str, namespace: str, items: dict):
        from neuromem.services.kv import KVService
        async with self._db.session() as session:
            svc = KVService(session)
            return await svc.batch_set(namespace, user_id, items)


class FilesFacade:
    """Files facade."""

    def __init__(self, db: Database, embedding: EmbeddingProvider, storage: ObjectStorage):
        self._db = db
        self._embedding = embedding
        self._storage = storage

    async def upload(self, user_id: str, filename: str, file_data: bytes, category: str = "general", tags: list[str] | None = None, metadata: dict | None = None):
        from neuromem.services.files import FileService
        async with self._db.session() as session:
            svc = FileService(session, self._embedding, self._storage)
            return await svc.upload(user_id, filename, file_data, category, tags, metadata)

    async def create_from_text(self, user_id: str, title: str, content: str, category: str = "general", tags: list[str] | None = None, metadata: dict | None = None):
        from neuromem.services.files import FileService
        async with self._db.session() as session:
            svc = FileService(session, self._embedding, self._storage)
            return await svc.create_from_text(user_id, title, content, category, tags, metadata)

    async def list(self, user_id: str, category: str | None = None, tags: list[str] | None = None, file_types: list[str] | None = None, limit: int = 50):
        from neuromem.services.files import FileService
        async with self._db.session() as session:
            svc = FileService(session, self._embedding, self._storage)
            return await svc.list_documents(user_id, category, tags, file_types, limit)

    async def search(self, user_id: str, query: str, limit: int = 5, file_types: list[str] | None = None, category: str | None = None, tags: list[str] | None = None) -> list[dict]:
        from neuromem.services.files import FileService
        async with self._db.session() as session:
            svc = FileService(session, self._embedding, self._storage)
            return await svc.search(user_id, query, limit, file_types, category, tags)

    async def get(self, user_id: str, file_id):
        from neuromem.services.files import FileService
        async with self._db.session() as session:
            svc = FileService(session, self._embedding, self._storage)
            return await svc.get_document(file_id, user_id)

    async def delete(self, user_id: str, file_id) -> bool:
        from neuromem.services.files import FileService
        async with self._db.session() as session:
            svc = FileService(session, self._embedding, self._storage)
            return await svc.delete_document(file_id, user_id)


class GraphFacade:
    """Graph facade."""

    def __init__(self, db: Database):
        self._db = db

    async def create_node(self, node_type, node_id: str, properties: dict | None = None, user_id: str | None = None):
        from neuromem.services.graph import GraphService
        async with self._db.session() as session:
            svc = GraphService(session)
            return await svc.create_node(node_type, node_id, properties, user_id)

    async def get_node(self, user_id: str, node_type, node_id: str):
        from neuromem.services.graph import GraphService
        async with self._db.session() as session:
            svc = GraphService(session)
            return await svc.get_node(node_type, node_id, user_id)

    async def update_node(self, user_id: str, node_type, node_id: str, properties: dict):
        from neuromem.services.graph import GraphService
        async with self._db.session() as session:
            svc = GraphService(session)
            return await svc.update_node(node_type, node_id, properties, user_id)

    async def delete_node(self, user_id: str, node_type, node_id: str):
        from neuromem.services.graph import GraphService
        async with self._db.session() as session:
            svc = GraphService(session)
            return await svc.delete_node(node_type, node_id, user_id)

    async def create_edge(self, source_type, source_id: str, edge_type, target_type, target_id: str, properties: dict | None = None, user_id: str | None = None):
        from neuromem.services.graph import GraphService
        async with self._db.session() as session:
            svc = GraphService(session)
            return await svc.create_edge(source_type, source_id, edge_type, target_type, target_id, properties, user_id)

    async def get_neighbors(self, user_id: str, node_type, node_id: str, edge_types=None, direction: str = "both", limit: int = 10):
        from neuromem.services.graph import GraphService
        async with self._db.session() as session:
            svc = GraphService(session)
            return await svc.get_neighbors(node_type, node_id, edge_types, direction, limit, user_id)

    async def find_path(self, user_id: str, source_type, source_id: str, target_type, target_id: str, max_depth: int = 3):
        from neuromem.services.graph import GraphService
        async with self._db.session() as session:
            svc = GraphService(session)
            return await svc.find_path(source_type, source_id, target_type, target_id, max_depth, user_id)
