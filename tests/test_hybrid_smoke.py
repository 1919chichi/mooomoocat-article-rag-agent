from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from mooomoocatrag.cli import app
from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChatResponse, ChunkMeta, IndexManifest, RetrievalResult


runner = CliRunner()


def make_settings(tmp_path, article_source_dir=None) -> Settings:
    return Settings(
        ARTICLE_SOURCE_DIR=str(article_source_dir or tmp_path / "articles"),
        DATA_DIR=str(tmp_path / "data"),
        OPENAI_COMPAT_BASE_URL="https://api.example.com/v1",
        OPENAI_COMPAT_API_KEY="test-key",
        EMBEDDING_MODEL="embedding-model",
        LLM_MODEL="llm-model",
        QDRANT_URL="http://127.0.0.1:6333",
        QDRANT_COLLECTION="mooomoocat_articles_v1",
        ELASTICSEARCH_URL="https://127.0.0.1:9200",
        ELASTICSEARCH_USERNAME="elastic",
        ELASTICSEARCH_PASSWORD="secret",
        ELASTICSEARCH_INDEX="mooomoocat_article_chunks_v1",
    )


def test_hybrid_runtime_smoke_flow(tmp_path):
    """Minimal smoke flow for ingest/search/chat with mocked backends."""
    source_root = tmp_path / "articles"
    source_root.mkdir()
    (source_root / "post.md").write_text("# 标题\n\n正文内容。", encoding="utf-8")
    settings = make_settings(tmp_path, source_root)

    chunk = ChunkMeta(
        chunk_id="chunk-1",
        article_id="article-1",
        chunk_index=0,
        nearest_heading="标题",
        text="这是一段可以展示的检索片段。" * 5,
        source_rel_path="post.md",
        title="文章标题",
        content_hash="hash",
        embedding_model="embedding-model",
        embedding_dimension=3,
    )
    manifest = IndexManifest(
        vector_store="qdrant",
        keyword_store="elasticsearch",
        retrieval_mode="hybrid_rrf",
        embedding_model="embedding-model",
        embedding_dimension=3,
        qdrant_collection="mooomoocat_articles_v1",
        elasticsearch_index="mooomoocat_article_chunks_v1",
        articles={"article-1": {"content_hash": "hash"}},
    )

    with (
        patch("mooomoocatrag.cli.get_settings", return_value=settings),
        patch("mooomoocatrag.cli.embed_texts", return_value=[[0.1, 0.2, 0.3]]),
        patch("mooomoocatrag.cli.upsert_dense_chunks"),
        patch("mooomoocatrag.cli.upsert_keyword_chunks"),
    ):
        ingest_result = runner.invoke(app, ["ingest"])

    assert ingest_result.exit_code == 0

    with (
        patch("mooomoocatrag.cli.get_settings", return_value=settings),
        patch("mooomoocatrag.cli.load_manifest", return_value=manifest),
        patch("mooomoocatrag.cli.check_consistency"),
        patch(
            "mooomoocatrag.cli.retrieve",
            return_value=[RetrievalResult(chunk=chunk, similarity=0.91, sources=["dense", "keyword"])],
        ),
    ):
        search_result = runner.invoke(app, ["search", "猫笔刀"])

    assert search_result.exit_code == 0
    assert "来源: dense+keyword" in search_result.output

    with (
        patch("mooomoocatrag.cli.get_settings", return_value=settings),
        patch("mooomoocatrag.cli.load_manifest", return_value=manifest),
        patch("mooomoocatrag.cli.check_consistency"),
        patch(
            "mooomoocatrag.cli.chat_turn",
            return_value=ChatResponse(
                answer="基于文章回答。[1]",
                citations=["[1] 文章标题 | post.md | chunk 0 | 小标题：标题"],
                retrieved_count=1,
            ),
        ),
    ):
        chat_result = runner.invoke(app, ["chat"], input="问题\n/exit\n")

    assert chat_result.exit_code == 0
    assert "基于文章回答。[1]" in chat_result.output
