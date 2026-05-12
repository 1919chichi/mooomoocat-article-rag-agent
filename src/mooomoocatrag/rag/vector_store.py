from __future__ import annotations

import chromadb
from chromadb.api.models.Collection import Collection

from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChunkMeta, IndexManifest


COLLECTION_NAME = "mooomoocat_articles"


def get_or_create_collection(
    config: Settings, embedding_model: str, embedding_dimension: int
) -> Collection:
    client = chromadb.PersistentClient(path=config.chroma_dir)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={
            "hnsw:space": config.VECTOR_DISTANCE_METRIC,
            "schema_version": "1",
            "embedding_model": embedding_model,
            "embedding_dimension": str(embedding_dimension),
        },
    )


def add_chunks(
    chunks: list[ChunkMeta], vectors: list[list[float]], config: Settings
) -> None:
    if not chunks:
        return

    collection = get_or_create_collection(
        config, chunks[0].embedding_model, chunks[0].embedding_dimension
    )

    ids = [c.chunk_id for c in chunks]
    documents = [c.text for c in chunks]
    metadatas = [
        {
            "article_id": c.article_id,
            "chunk_index": c.chunk_index,
            "nearest_heading": c.nearest_heading,
            "source_rel_path": c.source_rel_path,
            "title": c.title,
            "content_hash": c.content_hash,
            "embedding_model": c.embedding_model,
            "embedding_dimension": c.embedding_dimension,
        }
        for c in chunks
    ]

    collection.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=vectors)


def delete_chunks(chunk_ids: list[str], config: Settings) -> None:
    if not chunk_ids:
        return
    client = chromadb.PersistentClient(path=config.chroma_dir)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)
    collection.delete(ids=chunk_ids)


def query_similar(
    query_vector: list[float], top_k: int, config: Settings
) -> list[dict]:
    client = chromadb.PersistentClient(path=config.chroma_dir)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    overfetch = max(top_k * 3, top_k + 10)

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=overfetch,
        include=["distances", "metadatas", "documents"],
    )

    return [
        {
            "distances": results["distances"][0],
            "metadatas": results["metadatas"][0],
            "documents": results["documents"][0],
        }
    ]


def check_consistency(
    config: Settings,
    manifest: IndexManifest,
    embedding_dimension: int | None = None,
) -> None:
    errors: list[str] = []

    if manifest.embedding_model != config.EMBEDDING_MODEL:
        errors.append(
            f"embedding_model mismatch: manifest={manifest.embedding_model}, "
            f"config={config.EMBEDDING_MODEL}"
        )

    if (
        embedding_dimension is not None
        and manifest.embedding_dimension
        and manifest.embedding_dimension != embedding_dimension
    ):
        errors.append(
            f"embedding_dimension mismatch: manifest={manifest.embedding_dimension}, "
            f"current={embedding_dimension}"
        )

    if manifest.vector_store != config.VECTOR_STORE:
        errors.append(
            f"vector_store mismatch: manifest={manifest.vector_store}, "
            f"config={config.VECTOR_STORE}"
        )

    if manifest.vector_distance_metric != config.VECTOR_DISTANCE_METRIC:
        errors.append(
            f"vector_distance_metric mismatch: manifest={manifest.vector_distance_metric}, "
            f"config={config.VECTOR_DISTANCE_METRIC}"
        )

    stored_chunker = manifest.chunker_config or {}
    expected_chunker = {
        "chunk_target_min_chars": config.CHUNK_TARGET_MIN_CHARS,
        "chunk_target_max_chars": config.CHUNK_TARGET_MAX_CHARS,
        "chunk_overlap": config.CHUNK_OVERLAP,
    }
    if stored_chunker != expected_chunker:
        errors.append(
            f"chunker_config mismatch: manifest={stored_chunker}, "
            f"config={expected_chunker}"
        )

    if errors:
        msg = "\n".join(errors) + (
            "\n\nTo rebuild the index, run:\n  mooomoocatrag ingest --rebuild"
        )
        raise RuntimeError(msg)
