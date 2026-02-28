"""SQLAlchemy models for NeuroMemory.

_embedding_dims is set at runtime by NeuroMemory.__init__() before init_db().
"""

_embedding_dims: int = 1024

# Import all models to ensure they're registered with Base
from neuromem.models.base import Base, TimestampMixin
from neuromem.models.conversation import Conversation, ConversationSession
from neuromem.models.document import Document
from neuromem.models.emotion_profile import EmotionProfile
from neuromem.models.graph import EdgeType, GraphEdge, GraphNode, NodeType
from neuromem.models.kv import KeyValue
from neuromem.models.memory import Memory, Embedding
from neuromem.models.trait_evidence import TraitEvidence
from neuromem.models.memory_history import MemoryHistory
from neuromem.models.reflection_cycle import ReflectionCycle
from neuromem.models.memory_source import MemorySource

__all__ = [
    "Base",
    "TimestampMixin",
    "Memory",
    "Embedding",
    "TraitEvidence",
    "MemoryHistory",
    "ReflectionCycle",
    "MemorySource",
    "KeyValue",
    "Conversation",
    "ConversationSession",
    "Document",
    "GraphNode",
    "GraphEdge",
    "NodeType",
    "EdgeType",
    "EmotionProfile",
]
