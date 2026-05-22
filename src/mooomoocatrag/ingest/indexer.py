from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Iterable

from mooomoocatrag.config import Settings, get_settings
from mooomoocatrag.models import ArticleMeta, ChunkMeta, IndexManifest


def default_chunker_config(settings: Settings) -> dict[str, int]:
    """从 Settings 构造 manifest 存储用的 chunker_config 字典，用于一致性检查。"""
    return {
        "chunk_target_min_chars": settings.CHUNK_TARGET_MIN_CHARS,
        "chunk_target_max_chars": settings.CHUNK_TARGET_MAX_CHARS,
        "chunk_overlap": settings.CHUNK_OVERLAP,
    }


def build_empty_manifest(
    settings: Settings,
    source_root: str,
    embedding_dimension: int = 0,
) -> IndexManifest:
    """构造初始 manifest，用于首次建库或 --rebuild 时重置索引元数据。"""
    return IndexManifest(
        schema_version=1,
        source_root=source_root,
        vector_store=settings.VECTOR_STORE,
        keyword_store=settings.KEYWORD_STORE,
        retrieval_mode=settings.RETRIEVAL_MODE,
        vector_distance_metric=settings.VECTOR_DISTANCE_METRIC,
        embedding_provider="openai-compatible",
        embedding_model=settings.EMBEDDING_MODEL,
        embedding_dimension=embedding_dimension,
        qdrant_collection=settings.QDRANT_COLLECTION,
        elasticsearch_index=settings.ELASTICSEARCH_INDEX,
        chunker_config=default_chunker_config(settings),
        articles={},
    )


def load_manifest(data_dir: str) -> IndexManifest:
    """从 manifest 文件加载索引状态；文件不存在时返回空 manifest（使用当前配置默认值）。"""
    manifest_path = Path(data_dir) / "index_manifest.json"

    if not manifest_path.exists():
        settings = get_settings()
        return IndexManifest(
            schema_version=1,
            source_root="",
            vector_store=settings.VECTOR_STORE,
            keyword_store=settings.KEYWORD_STORE,
            retrieval_mode=settings.RETRIEVAL_MODE,
            vector_distance_metric=settings.VECTOR_DISTANCE_METRIC,
            embedding_provider="openai-compatible",
            embedding_model="",
            embedding_dimension=0,
            qdrant_collection=settings.QDRANT_COLLECTION,
            elasticsearch_index=settings.ELASTICSEARCH_INDEX,
            chunker_config=default_chunker_config(settings),
            articles={},
        )

    with open(manifest_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    settings = get_settings()
    return IndexManifest(
        schema_version=data.get("schema_version", 1),
        source_root=data.get("source_root", ""),
        vector_store=data.get("vector_store", settings.VECTOR_STORE),
        keyword_store=data.get("keyword_store", settings.KEYWORD_STORE),
        retrieval_mode=data.get("retrieval_mode", settings.RETRIEVAL_MODE),
        vector_distance_metric=data.get(
            "vector_distance_metric", settings.VECTOR_DISTANCE_METRIC
        ),
        embedding_provider=data.get("embedding_provider", "openai-compatible"),
        embedding_model=data.get("embedding_model", ""),
        embedding_dimension=data.get("embedding_dimension", 0),
        qdrant_collection=data.get("qdrant_collection", settings.QDRANT_COLLECTION),
        elasticsearch_index=data.get(
            "elasticsearch_index",
            settings.ELASTICSEARCH_INDEX,
        ),
        chunker_config=data.get("chunker_config", {}),
        articles=data.get("articles", {}),
    )


def save_manifest(manifest: IndexManifest, data_dir: str) -> None:
    """原子写入 manifest：先写临时文件，再用 os.replace 替换，防止写入中断导致文件损坏。"""
    data_dir_path = Path(data_dir)
    data_dir_path.mkdir(parents=True, exist_ok=True)

    manifest_path = data_dir_path / "index_manifest.json"

    with tempfile.NamedTemporaryFile(
        mode='w',
        encoding='utf-8',
        dir=data_dir_path,
        delete=False
    ) as tmp:
        json.dump({
            "schema_version": manifest.schema_version,
            "source_root": manifest.source_root,
            "vector_store": manifest.vector_store,
            "keyword_store": manifest.keyword_store,
            "retrieval_mode": manifest.retrieval_mode,
            "vector_distance_metric": manifest.vector_distance_metric,
            "embedding_provider": manifest.embedding_provider,
            "embedding_model": manifest.embedding_model,
            "embedding_dimension": manifest.embedding_dimension,
            "qdrant_collection": manifest.qdrant_collection,
            "elasticsearch_index": manifest.elasticsearch_index,
            "chunker_config": manifest.chunker_config,
            "articles": manifest.articles,
        }, tmp, ensure_ascii=False, indent=2)
        tmp_path = tmp.name

    os.replace(tmp_path, manifest_path)


def article_to_manifest_entry(
    article: ArticleMeta,
    chunks: list[ChunkMeta],
    existing_entry: dict | None = None,
    cleanup_chunk_ids: list[str] | None = None,
    deleted: bool = False,
) -> dict:
    """构造单篇文章的 manifest 条目，保留首次入库时间（created_at 不随重新索引更新）。"""
    created_at = (
        existing_entry.get("created_at")
        if existing_entry and existing_entry.get("created_at")
        else article.created_at.isoformat()
    )

    entry = {
        "title": article.title,
        "source_path": article.source_path,
        "source_rel_path": article.source_rel_path,
        "file_type": article.file_type,
        "content_hash": article.content_hash,
        "chunk_ids": [chunk.chunk_id for chunk in chunks],
        "created_at": created_at,
        "modified_time": article.modified_time.isoformat(),
        "updated_at": article.updated_at.isoformat(),
    }
    if cleanup_chunk_ids:
        entry["cleanup_chunk_ids"] = cleanup_chunk_ids
    if deleted:
        entry["deleted"] = True
    return entry


def find_deleted_article_ids(
    manifest: IndexManifest,
    current_article_ids: Iterable[str],
) -> list[str]:
    """返回在 manifest 中存在但当前扫描结果中不存在的 article_id，即已删除文章。"""
    current = set(current_article_ids)
    return [
        article_id
        for article_id in manifest.articles.keys()
        if article_id not in current
    ]
