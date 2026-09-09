import pytest
from unittest.mock import AsyncMock

from app.config import settings
from app.rag.embeddings import EmbeddingModel
from app.rag.retriever import ElasticsearchHybridRetriever, RAGRetriever


@pytest.mark.asyncio
async def test_rag_retriever_requires_elasticsearch_url(monkeypatch):
    monkeypatch.setattr(settings, "elasticsearch_url", None)

    retriever = RAGRetriever(top_k=3)

    with pytest.raises(RuntimeError, match="ELASTICSEARCH_URL"):
        await retriever.initialize()


def test_seed_knowledge_contains_health_metadata():
    retriever = RAGRetriever(top_k=3)

    seed_docs = retriever._load_seed_knowledge()

    assert len(seed_docs) >= 8
    assert all("content" in doc for doc in seed_docs)
    assert all("metadata" in doc for doc in seed_docs)
    assert any(doc["metadata"]["topic"] == "BMI" for doc in seed_docs)


def test_weighted_rrf_fuses_bm25_and_vector_results():
    retriever = ElasticsearchHybridRetriever(
        es_url="http://localhost:9200",
        index_name="test_health_knowledge",
        embedding_model=EmbeddingModel(model_name="mock"),
        top_k=3,
        candidate_k=5,
        vector_weight=0.7,
        bm25_weight=0.3,
    )

    bm25_results = [
        {
            "id": "k1",
            "content": "成年人每日推荐饮水量约为1500-2000毫升。",
            "metadata": {"topic": "hydration"},
            "raw_score": 10.0,
        },
        {
            "id": "k2",
            "content": "成年人每晚推荐睡眠时间为7-9小时。",
            "metadata": {"topic": "sleep"},
            "raw_score": 5.0,
        },
    ]
    vector_results = [
        {
            "id": "k1",
            "content": "成年人每日推荐饮水量约为1500-2000毫升。",
            "metadata": {"topic": "hydration"},
            "raw_score": 0.9,
        },
        {
            "id": "k3",
            "content": "成年人每周推荐进行至少150分钟中等强度有氧运动。",
            "metadata": {"topic": "aerobic"},
            "raw_score": 0.8,
        },
    ]

    results = retriever._fuse_ranked_results(
        [
            ("bm25", bm25_results, retriever.bm25_weight),
            ("vector", vector_results, retriever.vector_weight),
        ]
    )

    assert results[0]["id"] == "k1"
    assert set(results[0]["retrieval"]["sources"]) == {"bm25", "vector"}
    assert results[0]["retrieval"]["raw_scores"]["bm25"] == 10.0
    assert results[0]["retrieval"]["raw_scores"]["vector"] == 0.9


def test_dashscope_embedding_uses_compatible_api():
    captured = {}

    def fake_post_json(url, payload):
        captured["url"] = url
        captured["payload"] = payload
        return {
            "data": [
                {"index": 0, "embedding": [1.0, 0.0, 0.0, 0.0]},
                {"index": 1, "embedding": [0.0, 1.0, 0.0, 0.0]},
            ]
        }

    model = EmbeddingModel(
        model_name="dashscope-text-embedding-v4",
        api_key="test-key",
        api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        dimension=4,
        batch_size=10,
    )
    model._post_json = fake_post_json

    embeddings = model.encode(["建议多大的身体活动量？", "成年人运动建议"])

    assert captured["url"].endswith("/embeddings")
    assert captured["payload"]["model"] == "text-embedding-v4"
    assert captured["payload"]["dimensions"] == 4
    assert captured["payload"]["input"] == ["建议多大的身体活动量？", "成年人运动建议"]
    assert embeddings == [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]


def test_dashscope_embedding_requires_api_key():
    model = EmbeddingModel(model_name="dashscope-text-embedding-v4", api_key="", dimension=4)

    with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY"):
        model.encode("成年人运动建议")


@pytest.mark.asyncio
async def test_vector_search_skips_dimension_mismatch():
    retriever = ElasticsearchHybridRetriever(
        es_url="http://localhost:9200",
        index_name="test_health_knowledge",
        embedding_model=EmbeddingModel(model_name="mock"),
        top_k=3,
    )
    retriever._client = AsyncMock()
    retriever._client.search.side_effect = RuntimeError(
        "failed to create query: the query vector has a different dimension [1024] than the index vectors [768]"
    )

    results = await retriever._vector_search([0.1] * 1024)

    assert results == []
