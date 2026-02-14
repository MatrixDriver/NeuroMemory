"""NeuroMemory - Memory management framework for AI agents."""

from neuromemory._core import ExtractionStrategy, NeuroMemory
from neuromemory.db import Database
from neuromemory.models.emotion_profile import EmotionProfile
from neuromemory.models.graph import EdgeType, NodeType
from neuromemory.providers.embedding import EmbeddingProvider
from neuromemory.providers.llm import LLMProvider
from neuromemory.providers.openai_embedding import OpenAIEmbedding
from neuromemory.providers.openai_llm import OpenAILLM
from neuromemory.providers.siliconflow import SiliconFlowEmbedding

try:
    from neuromemory.providers.sentence_transformer import SentenceTransformerEmbedding
except ImportError:
    SentenceTransformerEmbedding = None
from neuromemory.services.graph_memory import GraphMemoryService
from neuromemory.services.reflection import ReflectionService
from neuromemory.storage.base import ObjectStorage
from neuromemory.storage.s3 import S3Storage

__all__ = [
    "ExtractionStrategy",
    "NeuroMemory",
    "Database",
    "EmotionProfile",
    "EmbeddingProvider",
    "LLMProvider",
    "SiliconFlowEmbedding",
    "OpenAIEmbedding",
    "OpenAILLM",
    "SentenceTransformerEmbedding",
    "ObjectStorage",
    "S3Storage",
    "NodeType",
    "EdgeType",
    "GraphMemoryService",
    "ReflectionService",
]
