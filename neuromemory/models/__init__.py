"""SQLAlchemy models for NeuroMemory.

_embedding_dims is set at runtime by NeuroMemory.__init__() before init_db().
"""

_embedding_dims: int = 1024

# Import all models to ensure they're registered with Base
from neuromemory.models.base import Base, TimestampMixin
from neuromemory.models.conversation import Conversation, ConversationSession
from neuromemory.models.document import Document
from neuromemory.models.emotion_profile import EmotionProfile
from neuromemory.models.graph import EdgeType, GraphEdge, GraphNode, NodeType
from neuromemory.models.kv import KeyValue
from neuromemory.models.memory import Embedding

__all__ = [
    "Base",
    "TimestampMixin",
    "Embedding",
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
