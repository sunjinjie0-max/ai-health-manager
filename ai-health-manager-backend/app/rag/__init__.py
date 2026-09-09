"""RAG (Retrieval-Augmented Generation) module.

This module provides retrieval-augmented generation capabilities
for the AI Health Manager, including:
- Vector and keyword-based retrieval
- Document reranking
- Knowledge base management
- Embedding generation
"""

from .embeddings import EmbeddingModel
from .knowledge_base import KnowledgeBase
from .retriever import RAGRetriever
from .reranker import Reranker

__all__ = [
    "EmbeddingModel",
    "KnowledgeBase",
    "RAGRetriever",
    "Reranker",
]
