"""neuromem - Memory management framework for AI agents."""

__version__ = "0.7.0"

from neuromem._core import ExtractionStrategy, NeuroMemory
from neuromem.db import Database
from neuromem.models.emotion_profile import EmotionProfile
from neuromem.models.graph import EdgeType, NodeType
from neuromem.providers.embedding import EmbeddingProvider
from neuromem.providers.llm import LLMProvider
from neuromem.providers.openai_embedding import OpenAIEmbedding
from neuromem.providers.openai_llm import OpenAILLM
from neuromem.providers.siliconflow import SiliconFlowEmbedding

try:
    from neuromem.providers.sentence_transformer import SentenceTransformerEmbedding
except ImportError:
    SentenceTransformerEmbedding = None
from neuromem.services.graph_memory import GraphMemoryService
from neuromem.services.reflection import ReflectionService
from neuromem.storage.base import ObjectStorage
from neuromem.storage.s3 import S3Storage

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
