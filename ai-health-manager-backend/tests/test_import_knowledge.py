import json

from scripts.import_knowledge import (
    RawDocument,
    build_documents,
    clean_text,
    extract_html_text,
    read_json_records,
)
from app.rag.knowledge_base import KnowledgeBase


def test_clean_text_removes_page_numbers_and_normalizes_spacing():
    text = "  成年人  每周运动 150 分钟。\n\n\n第 12 页\n\n  睡眠建议 7-9 小时。  "

    cleaned = clean_text(text)

    assert "第 12 页" not in cleaned
    assert "成年人 每周运动 150 分钟。" in cleaned
    assert "睡眠建议 7-9 小时。" in cleaned


def test_extract_html_text_prefers_main_content():
    html = """
    <html>
      <head><title>健康指南</title></head>
      <body>
        <nav>首页 导航</nav>
        <main><h1>运动建议</h1><p>成年人每周建议进行有氧运动。</p></main>
        <footer>版权信息</footer>
      </body>
    </html>
    """.encode("utf-8")

    text, title = extract_html_text(html)

    assert title == "健康指南"
    assert "运动建议" in text
    assert "首页 导航" not in text
    assert "版权信息" not in text


def test_read_jsonl_records(tmp_path):
    jsonl = tmp_path / "knowledge.jsonl"
    jsonl.write_text(
        json.dumps(
            {
                "title": "睡眠建议",
                "content": "成年人每晚推荐睡眠7-9小时。",
                "source": "guideline",
                "metadata": {"category": "lifestyle", "topic": "sleep"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    records = read_json_records(jsonl)

    assert len(records) == 1
    assert records[0].title == "睡眠建议"
    assert records[0].metadata["topic"] == "sleep"


def test_build_documents_chunks_and_adds_metadata():
    raw = RawDocument(
        title="成年人运动指南",
        content="成年人每周推荐进行至少150分钟中等强度有氧运动。运动前应充分热身，运动后拉伸放松。",
        source="unit-test",
        source_type="text",
        metadata={"authority": "test"},
    )

    docs = build_documents(
        [raw],
        category="exercise",
        topic="aerobic",
        global_metadata={"version": "2026"},
        chunk_size=30,
        chunk_overlap=5,
    )

    assert len(docs) >= 2
    assert docs[0]["title"] == "成年人运动指南"
    assert docs[0]["metadata"]["category"] == "exercise"
    assert docs[0]["metadata"]["topic"] == "aerobic"
    assert docs[0]["metadata"]["authority"] == "test"
    assert docs[0]["metadata"]["version"] == "2026"
    assert docs[0]["metadata"]["chunk_size"] == 30
    assert docs[0]["metadata"]["chunk_overlap"] == 5
    assert docs[0]["content"]


def test_chunk_text_honors_explicit_zero_overlap():
    knowledge_base = KnowledgeBase(
        embedding_model=None,
        chunk_size=5,
        chunk_overlap=2,
        index_name="unused",
    )

    chunks = knowledge_base.chunk_text("abcdefghij", chunk_overlap=0)

    assert [chunk["start"] for chunk in chunks] == [0, 5]
    assert [chunk["end"] for chunk in chunks] == [5, 10]


def test_chunk_text_advances_when_sentence_boundary_is_inside_overlap():
    knowledge_base = KnowledgeBase(
        embedding_model=None,
        chunk_size=10,
        chunk_overlap=4,
        index_name="unused",
    )

    text = "A。 bcdefghijklmnop"
    chunks = knowledge_base.chunk_text(text)

    starts = [chunk["start"] for chunk in chunks]
    assert starts == sorted(set(starts))
    assert chunks[0]["end"] == 2
    assert chunks[1]["start"] == 2
    assert chunks[-1]["end"] == len(text)
