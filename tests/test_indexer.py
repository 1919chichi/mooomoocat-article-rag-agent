from __future__ import annotations

from datetime import datetime

from mooomoocatrag.config import Settings
from mooomoocatrag.ingest.indexer import (
    article_to_manifest_entry,
    build_empty_manifest,
    default_chunker_config,
    find_deleted_article_ids,
    load_manifest,
)
from mooomoocatrag.models import ArticleMeta, ChunkMeta


class TestIndexerHelpers:
    def test_load_manifest_uses_current_chunker_config_keys(self, tmp_path):
        manifest = load_manifest(str(tmp_path))

        assert manifest.chunker_config == {
            "chunk_target_min_chars": 600,
            "chunk_target_max_chars": 1000,
            "chunk_overlap": 100,
        }

    def test_default_chunker_config_uses_settings_values(self):
        settings = Settings(
            CHUNK_TARGET_MIN_CHARS=300,
            CHUNK_TARGET_MAX_CHARS=900,
            CHUNK_OVERLAP=80,
        )

        assert default_chunker_config(settings) == {
            "chunk_target_min_chars": 300,
            "chunk_target_max_chars": 900,
            "chunk_overlap": 80,
        }

    def test_build_empty_manifest_records_runtime_index_config(self):
        settings = Settings(
            VECTOR_STORE="chroma",
            VECTOR_DISTANCE_METRIC="cosine",
            EMBEDDING_MODEL="embedding-model",
            CHUNK_TARGET_MIN_CHARS=300,
            CHUNK_TARGET_MAX_CHARS=900,
            CHUNK_OVERLAP=80,
        )

        manifest = build_empty_manifest(
            settings,
            source_root="/tmp/articles",
            embedding_dimension=1536,
        )

        assert manifest.source_root == "/tmp/articles"
        assert manifest.embedding_model == "embedding-model"
        assert manifest.embedding_dimension == 1536
        assert manifest.chunker_config == default_chunker_config(settings)

    def test_article_to_manifest_entry_includes_chunk_ids_and_relative_path(self):
        now = datetime(2026, 5, 8, 12, 0, 0)
        article = ArticleMeta(
            article_id="article-1",
            title="标题",
            source_path="/tmp/articles/nested/post.md",
            source_rel_path="nested/post.md",
            file_type="markdown",
            content_hash="hash-1",
            modified_time=now,
            created_at=now,
            updated_at=now,
        )
        chunks = [
            ChunkMeta(
                chunk_id="chunk-1",
                article_id="article-1",
                chunk_index=0,
                nearest_heading="标题",
                text="正文",
                source_rel_path="nested/post.md",
                title="标题",
                content_hash="hash-1",
                embedding_model="embedding-model",
                embedding_dimension=1536,
            )
        ]

        entry = article_to_manifest_entry(article, chunks)

        assert entry["source_rel_path"] == "nested/post.md"
        assert entry["chunk_ids"] == ["chunk-1"]
        assert entry["content_hash"] == "hash-1"

    def test_find_deleted_article_ids(self):
        manifest = build_empty_manifest(Settings(), source_root="/tmp/articles")
        manifest.articles = {
            "article-1": {"source_rel_path": "a.md"},
            "article-2": {"source_rel_path": "b.md"},
        }

        assert find_deleted_article_ids(manifest, {"article-2"}) == ["article-1"]
