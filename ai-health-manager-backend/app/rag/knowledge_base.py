"""Knowledge Base for RAG system."""

import logging
from typing import Any, Dict, List, Optional

from app.core.time import utc_isoformat

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """Knowledge Base for RAG system.

    This class manages the knowledge base including:
    - Document storage and indexing
    - Chunking strategies
    - Vector embedding generation
    - Index management

    Attributes:
        embedding_model: Model for generating embeddings
        es_client: Elasticsearch client
        chunk_size: Size of text chunks
        chunk_overlap: Overlap between chunks
        index_name: Name of the knowledge base index
    """

    def __init__(
        self,
        embedding_model: Any,
        es_client: Optional[Any] = None,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        index_name: str = "knowledge_base",
    ):
        """Initialize the knowledge base.

        Args:
            embedding_model: Embedding model instance
            es_client: Elasticsearch client
            chunk_size: Size of text chunks
            chunk_overlap: Overlap between chunks
            index_name: Name of the index
        """
        self.embedding_model = embedding_model
        self.es_client = es_client
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.index_name = index_name

        logger.info(
            f"Initialized KnowledgeBase (chunk_size={chunk_size}, "
            f"index={index_name})"
        )

    def chunk_text(
        self,
        text: str,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Split text into chunks.

        Uses a sliding window approach with overlap.

        Args:
            text: Text to chunk
            chunk_size: Size of each chunk
            chunk_overlap: Overlap between chunks

        Returns:
            List of chunks with metadata
        """
        size = self.chunk_size if chunk_size is None else chunk_size
        overlap = self.chunk_overlap if chunk_overlap is None else chunk_overlap

        if size <= 0:
            raise ValueError("chunk_size must be greater than 0")
        if overlap < 0 or overlap >= size:
            raise ValueError("chunk_overlap must be greater than or equal to 0 and smaller than chunk_size")

        if len(text) <= size:
            return [{"text": text, "start": 0, "end": len(text)}]

        chunks = []
        start = 0
        chunk_id = 0

        while start < len(text):
            end = min(start + size, len(text))

            # Try to break at a sentence boundary
            if end < len(text):
                # Look for sentence endings
                for i in range(min(end, len(text) - 1), start, -1):
                    if text[i] in ".。！？!?" and (i + 1 >= len(text) or text[i + 1] in " \n"):
                        end = i + 1
                        break

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append({
                    "text": chunk_text,
                    "start": start,
                    "end": end,
                    "chunk_id": chunk_id,
                })
                chunk_id += 1

            if end >= len(text):
                break

            next_start = end - overlap

            if next_start <= start:
                # A sentence boundary can fall inside the overlap window. In
                # that case reusing the overlap would keep the cursor in place
                # or move it backwards, so omit overlap for this short chunk.
                next_start = end

            start = next_start
            if start >= len(text):
                break

        return chunks

    async def add_document(
        self,
        document: Dict[str, Any],
        generate_embeddings: bool = True,
    ) -> List[str]:
        """Add a document to the knowledge base.

        Args:
            document: Document to add (with content, metadata)
            generate_embeddings: Whether to generate embeddings

        Returns:
            List of chunk IDs
        """
        content = document.get("content", "")
        if not content:
            logger.warning("[add_document] Empty document content")
            return []

        # Chunk the document
        chunks = self.chunk_text(content)

        # Generate embeddings
        if generate_embeddings and self.embedding_model:
            texts = [chunk["text"] for chunk in chunks]
            embeddings = self.embedding_model.encode(texts)

            for i, chunk in enumerate(chunks):
                chunk["embedding"] = embeddings[i]

        # Index chunks
        chunk_ids = []
        for chunk in chunks:
            chunk_id = await self._index_chunk(chunk, document.get("metadata", {}))
            chunk_ids.append(chunk_id)

        logger.info(f"[add_document] Added document with {len(chunks)} chunks")

        return chunk_ids

    async def _index_chunk(
        self,
        chunk: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> str:
        """Index a single chunk.

        Args:
            chunk: Chunk to index
            metadata: Document metadata

        Returns:
            Chunk ID
        """
        import uuid

        chunk_id = str(uuid.uuid4())

        # Prepare document for indexing
        doc = {
            "id": chunk_id,
            "content": chunk["text"],
            "chunk_id": chunk.get("chunk_id", 0),
            "start": chunk.get("start", 0),
            "end": chunk.get("end", 0),
            "timestamp": utc_isoformat(),
            **metadata,
        }

        # Add embedding if available
        if "embedding" in chunk:
            doc["embedding"] = chunk["embedding"]

        # Index in Elasticsearch if available
        if self.es_client:
            try:
                await self.es_client.index(
                    index=self.index_name,
                    id=chunk_id,
                    document=doc,
                )
            except Exception as e:
                logger.error(f"[_index_chunk] ES indexing failed: {e}")

        return chunk_id

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search the knowledge base.

        Args:
            query: Search query
            top_k: Number of results
            filters: Optional filters

        Returns:
            List of search results
        """
        # This is a simplified search method
        # In production, this would use the retriever

        results = []

        # Mock search for development
        if self.es_client:
            try:
                # Build ES query
                es_query = {
                    "query": {
                        "multi_match": {
                            "query": query,
                            "fields": ["content^3", "title^2"],
                        }
                    },
                    "size": top_k,
                }

                if filters:
                    es_query["query"] = {
                        "bool": {
                            "must": [es_query["query"]],
                            "filter": [{"term": {k: v}} for k, v in filters.items()],
                        }
                    }

                # Execute search
                response = await self.es_client.search(
                    index=self.index_name,
                    body=es_query,
                )

                # Parse results
                for hit in response["hits"]["hits"]:
                    results.append({
                        "id": hit["_id"],
                        "content": hit["_source"]["content"],
                        "score": hit["_score"],
                        "metadata": {k: v for k, v in hit["_source"].items() if k not in ["content", "embedding"]},
                    })

            except Exception as e:
                logger.error(f"[search] ES search failed: {e}")

        return results[:top_k]
