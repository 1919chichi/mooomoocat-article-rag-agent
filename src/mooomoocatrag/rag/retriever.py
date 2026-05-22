from __future__ import annotations

import logging
import math
from collections import OrderedDict

from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChunkMeta, IndexManifest, RetrievalResult
from mooomoocatrag.rag.embeddings import embed_texts
from mooomoocatrag.rag.vector_store import query_dense, query_keyword

logger = logging.getLogger(__name__)


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

    dense_results: list[dict] = []
    keyword_results: list[dict] = []

    try:
        dense_results = query_dense(query_vector, config.HYBRID_DENSE_TOP_K, config)
    except Exception as exc:  # pragma: no cover - exercised via mocks
        logger.warning("Dense retrieval failed, falling back to remaining backends: %s", exc)

    try:
        keyword_results = query_keyword(query, config.HYBRID_KEYWORD_TOP_K, config)
    except Exception as exc:  # pragma: no cover - exercised via mocks
        logger.warning("Keyword retrieval failed, falling back to remaining backends: %s", exc)

    fused_results = _fuse_candidates(
        dense_results,
        keyword_results,
        config.HYBRID_RRF_K,
    )
    if not fused_results:
        return []

    candidates: list[tuple[RetrievalResult, float]] = []
    for candidate in fused_results:
        metadata = candidate["metadata"]
        document = candidate.get("document", "") or metadata.get("text", "")
        similarity = float(candidate["score"])
        chunk = ChunkMeta(
            chunk_id=str(candidate["chunk_id"]),
            article_id=metadata["article_id"],
            chunk_index=int(metadata["chunk_index"]),
            nearest_heading=metadata.get("nearest_heading", ""),
            text=document,
            source_rel_path=metadata["source_rel_path"],
            title=metadata["title"],
            content_hash=metadata["content_hash"],
            embedding_model=metadata["embedding_model"],
            embedding_dimension=int(metadata["embedding_dimension"]),
        )
        candidates.append(
            (
                RetrievalResult(
                    chunk=chunk,
                    similarity=similarity,
                    sources=list(candidate.get("sources", [])),
                ),
                similarity,
            )
        )

    # 防止 ingest 中断或删除同步失败时，残留 chunk 被返回给用户
    filtered: list[tuple[RetrievalResult, float]] = []
    for result, similarity in candidates:
        article_data = manifest.articles.get(result.chunk.article_id)
        if article_data is None:
            continue
        if article_data.get("deleted"):
            continue
        # content_hash 不匹配说明文章已更新但旧 chunk 未清理完毕，跳过
        if article_data.get("content_hash") != result.chunk.content_hash:
            continue
        filtered.append((result, similarity))

    threshold_filtered = [
        (r, s) for r, s in filtered if s >= config.SIMILARITY_THRESHOLD
    ]

    # Sort by similarity descending
    threshold_filtered.sort(key=lambda x: x[1], reverse=True)

    # token 预算截断：按相似度从高到低塞入 chunk，超出 RAG_CONTEXT_TOKEN_BUDGET 即停止
    # 字符数估算：estimated_tokens = ceil(chars / 1.5)，适用于中文内容
    budget = config.RAG_CONTEXT_TOKEN_BUDGET
    budgeted: list[tuple[RetrievalResult, float]] = []
    current_tokens = 0

    for result, similarity in threshold_filtered:
        chunk_tokens = math.ceil(len(result.chunk.text) / 1.5)
        if current_tokens + chunk_tokens > budget:
            # 预算已满；若列表为空且该 chunk 单独能放入，则至少保留一条结果
            if not budgeted and chunk_tokens <= budget:
                budgeted.append((result, similarity))
                current_tokens += chunk_tokens
            break
        budgeted.append((result, similarity))
        current_tokens += chunk_tokens

    # 最终按 HYBRID_FINAL_TOP_K 截断（预算控制优先，top_k 为第二道限制）
    final_top_k = config.HYBRID_FINAL_TOP_K or config.TOP_K
    final_results = [r for r, _ in budgeted[:final_top_k]]

    return final_results


def _fuse_candidates(
    dense_results: list[dict],
    keyword_results: list[dict],
    rrf_k: int,
) -> list[dict]:
    """用 RRF（Reciprocal Rank Fusion）融合 dense 和 keyword 两路检索结果。

    RRF 公式：score += 1 / (k + rank)，k 由调用方传入（通常为 60），rank 从 1 开始。
    归一化：将 raw_score 除以单路命中时的最大可能分数，映射到 0-1 范围。
    """
    aggregated: OrderedDict[str, dict] = OrderedDict()

    for source_results in (dense_results, keyword_results):
        for rank, candidate in enumerate(source_results, start=1):
            chunk_id = str(candidate["chunk_id"])
            entry = aggregated.setdefault(
                chunk_id,
                {
                    "chunk_id": chunk_id,
                    "metadata": candidate["metadata"],
                    "document": candidate.get("document", ""),
                    "raw_score": 0.0,
                    "sources": [],
                },
            )
            entry["raw_score"] += 1.0 / (rrf_k + rank)
            source = candidate.get("source")
            if source and source not in entry["sources"]:
                entry["sources"].append(source)
            if not entry.get("document") and candidate.get("document"):
                entry["document"] = candidate["document"]

    if not aggregated:
        return []

    # 归一化基准：两路都在第 1 名时的理论最大分数
    source_lists = (dense_results, keyword_results)
    num_sources = len(source_lists)
    max_possible_score = num_sources * (1.0 / (rrf_k + 1))
    fused: list[dict] = []
    for entry in aggregated.values():
        fused.append(
            {
                "chunk_id": entry["chunk_id"],
                "metadata": entry["metadata"],
                "document": entry["document"],
                "score": min(entry["raw_score"] / max_possible_score, 1.0)
                if max_possible_score
                else 0.0,
                "sources": entry["sources"],
            }
        )

    fused.sort(key=lambda item: item["score"], reverse=True)
    return fused


