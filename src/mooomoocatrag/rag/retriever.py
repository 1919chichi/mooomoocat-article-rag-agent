from __future__ import annotations

import math

from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChunkMeta, IndexManifest, RetrievalResult
from mooomoocatrag.rag.embeddings import embed_texts
from mooomoocatrag.rag.vector_store import query_similar


def retrieve(
    query: str, config: Settings, manifest: IndexManifest
) -> list[RetrievalResult]:
    """
    Retrieve relevant chunks for a query.

    Args:
        query: The search query
        config: Settings object with TOP_K, SIMILARITY_THRESHOLD, etc.
        manifest: IndexManifest containing article metadata

    Returns:
        List of RetrievalResult sorted by similarity descending
    """
    # Embed the query
    query_vectors = embed_texts([query], config)
    if not query_vectors:
        return []

    query_vector = query_vectors[0]

    # Query vector store
    raw_results = query_similar(query_vector, config.TOP_K, config)
    if not raw_results or not raw_results[0].get("distances"):
        return []

    distances = raw_results[0]["distances"]
    metadatas = raw_results[0]["metadatas"]
    documents = raw_results[0]["documents"]

    # Build candidate results with similarity scores
    candidates: list[tuple[RetrievalResult, float]] = []
    for i, distance in enumerate(distances):
        metadata = metadatas[i]
        document = documents[i] if i < len(documents) else ""

        # Convert cosine distance to similarity (cosine distance is 0-2, cosine similarity is -1 to 1)
        # For normalized vectors with cosine distance metric: similarity = 1 - distance
        # But Chroma's cosine distance is already in 0-2 range, so we clamp
        similarity = max(0.0, min(1.0, 1.0 - distance))

        chunk = ChunkMeta(
            chunk_id=f"{metadata['article_id']}_{metadata['chunk_index']}",
            article_id=metadata["article_id"],
            chunk_index=metadata["chunk_index"],
            nearest_heading=metadata.get("nearest_heading", ""),
            text=document,
            source_rel_path=metadata["source_rel_path"],
            title=metadata["title"],
            content_hash=metadata["content_hash"],
            embedding_model=metadata["embedding_model"],
            embedding_dimension=int(metadata["embedding_dimension"]),
        )
        candidates.append((RetrievalResult(chunk=chunk, similarity=similarity), similarity))

    # Filter by manifest: only keep chunks where article exists and content_hash matches
    filtered: list[tuple[RetrievalResult, float]] = []
    for result, similarity in candidates:
        article_data = manifest.articles.get(result.chunk.article_id)
        if article_data is None:
            continue
        if article_data.get("content_hash") != result.chunk.content_hash:
            continue
        filtered.append((result, similarity))

    # Filter by similarity threshold
    threshold_filtered = [
        (r, s) for r, s in filtered if s >= config.SIMILARITY_THRESHOLD
    ]

    # Sort by similarity descending
    threshold_filtered.sort(key=lambda x: x[1], reverse=True)

    # Budget-aware truncation by token count
    budget = config.RAG_CONTEXT_TOKEN_BUDGET
    budgeted: list[tuple[RetrievalResult, float]] = []
    current_tokens = 0

    for result, similarity in threshold_filtered:
        # Estimate tokens as ceil(chars / 1.5)
        chunk_tokens = math.ceil(len(result.chunk.text) / 1.5)
        if current_tokens + chunk_tokens > budget:
            # Try to see if adding this chunk would exceed budget
            # If budgeted is empty and this chunk alone fits, add it
            if not budgeted:
                if chunk_tokens <= budget:
                    budgeted.append((result, similarity))
                    current_tokens += chunk_tokens
            # Otherwise stop
            break
        budgeted.append((result, similarity))
        current_tokens += chunk_tokens

    # Final top_k truncation
    final_results = [r for r, _ in budgeted[: config.TOP_K]]

    return final_results


def _estimate_tokens(text: str) -> int:
    """Estimate token count for text."""
    return math.ceil(len(text) / 1.5)
