"""Test script for RAG system.

This script tests the RAG retrieval functionality.
"""

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

logger = logging.getLogger(__name__)


async def test_embeddings():
    """Test embedding model."""
    print("\n" + "="*60)
    print("Testing EmbeddingModel")
    print("="*60 + "\n")
    
    from app.rag.embeddings import EmbeddingModel
    
    model = EmbeddingModel(model_name="mock")
    
    # Test single text
    text = "这是一个测试文本"
    embedding = model.encode(text)
    print(f"Single text embedding: dim={len(embedding[0])}")
    
    # Test batch
    texts = ["文本1", "文本2", "文本3"]
    embeddings = model.encode(texts)
    print(f"Batch embeddings: count={len(embeddings)}, dim={len(embeddings[0])}")
    
    # Test similarity
    sim = model.similarity(embeddings[0], embeddings[1])
    print(f"Similarity between text1 and text2: {sim:.4f}")
    
    print("\n✅ EmbeddingModel test passed!")


async def main():
    """Run all tests."""
    try:
        await test_embeddings()
        print("\n" + "="*60)
        print("All RAG tests completed!")
        print("="*60 + "\n")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
