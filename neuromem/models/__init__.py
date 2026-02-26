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
from neuromem.models.memory import Embedding

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
