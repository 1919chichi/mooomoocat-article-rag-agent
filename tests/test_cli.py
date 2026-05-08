from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from mooomoocatrag.cli import app
from mooomoocatrag.config import Settings
from mooomoocatrag.ingest.indexer import load_manifest
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
    )


def test_ingest_indexes_articles_and_writes_manifest(tmp_path):
    source_root = tmp_path / "articles"
    source_root.mkdir()
    (source_root / "post.md").write_text("# 标题\n\n正文内容。", encoding="utf-8")
    settings = make_settings(tmp_path, source_root)

    with (
        patch("mooomoocatrag.cli.get_settings", return_value=settings),
        patch("mooomoocatrag.cli.embed_texts", return_value=[[0.1, 0.2, 0.3]]),
        patch("mooomoocatrag.cli.add_chunks") as mock_add_chunks,
    ):
        result = runner.invoke(app, ["ingest"])

    assert result.exit_code == 0
    assert "索引完成：扫描 1 个文件" in result.output
    assert mock_add_chunks.called

    manifest = load_manifest(settings.DATA_DIR)
    assert manifest.embedding_model == "embedding-model"
    assert manifest.embedding_dimension == 3
    assert len(manifest.articles) == 1
    article_entry = next(iter(manifest.articles.values()))
    assert article_entry["source_rel_path"] == "post.md"
    assert article_entry["chunk_ids"]


def test_search_outputs_retrieved_chunks(tmp_path):
    settings = make_settings(tmp_path)
    chunk = ChunkMeta(
        chunk_id="chunk-1",
        article_id="article-1",
        chunk_index=0,
        nearest_heading="标题",
        text="这是一段可以展示的检索片段。" * 10,
        source_rel_path="post.md",
        title="文章标题",
        content_hash="hash",
        embedding_model="embedding-model",
        embedding_dimension=3,
    )
    manifest = IndexManifest(
        embedding_model="embedding-model",
        embedding_dimension=3,
        articles={"article-1": {"content_hash": "hash"}},
    )

    with (
        patch("mooomoocatrag.cli.get_settings", return_value=settings),
        patch("mooomoocatrag.cli.load_manifest", return_value=manifest),
        patch("mooomoocatrag.cli.check_consistency"),
        patch(
            "mooomoocatrag.cli.retrieve",
            return_value=[RetrievalResult(chunk=chunk, similarity=0.87)],
        ),
    ):
        result = runner.invoke(app, ["search", "猫笔刀"])

    assert result.exit_code == 0
    assert "[1] 相似度: 0.87 | 文章标题 | post.md | chunk 0 | 小标题：标题" in result.output
    assert "共 1 个结果" in result.output


def test_chat_runs_interactive_turn_and_prints_citations(tmp_path):
    settings = make_settings(tmp_path)
    manifest = IndexManifest(
        embedding_model="embedding-model",
        embedding_dimension=3,
        articles={"article-1": {"content_hash": "hash"}},
    )
    response = ChatResponse(
        answer="基于文章回答。[1]",
        citations=["[1] 文章标题 | post.md | chunk 0 | 小标题：标题"],
        retrieved_count=1,
    )

    with (
        patch("mooomoocatrag.cli.get_settings", return_value=settings),
        patch("mooomoocatrag.cli.load_manifest", return_value=manifest),
        patch("mooomoocatrag.cli.check_consistency"),
        patch("mooomoocatrag.cli.chat_turn", return_value=response) as mock_chat_turn,
    ):
        result = runner.invoke(app, ["chat"], input="问题\n/exit\n")

    assert result.exit_code == 0
    assert "基于文章回答。[1]" in result.output
    assert "[1] 文章标题 | post.md | chunk 0 | 小标题：标题" in result.output
    assert "会话结束：共提问 1 次，引用 1 篇文章" in result.output
    mock_chat_turn.assert_called_once()
