from __future__ import annotations

import math
from typing import Any

from openai import OpenAI

from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChatResponse, IndexManifest, RetrievalResult
from mooomoocatrag.rag.prompt import build_rag_prompt, format_citations
from mooomoocatrag.rag.retriever import retrieve


# Default response when no relevant content is found
INSUFFICIENT_CONTENT_RESPONSE = "当前猫笔刀文章库中没有找到足够依据。"

# Backward-compatible alias for existing imports.
NO_INSUFFICIENT_CONTENTResponse = INSUFFICIENT_CONTENT_RESPONSE

VALID_HISTORY_ROLES = {"user", "assistant"}


def _estimate_tokens(text: str) -> int:
    """Estimate token count for text."""
    return math.ceil(len(text) / 1.5)


def _recent_valid_history(history: list[dict], max_messages: int) -> list[dict]:
    valid_history = [
        {"role": turn.get("role", "user"), "content": turn.get("content", "")}
        for turn in history
        if turn.get("role", "user") in VALID_HISTORY_ROLES
    ]
    return valid_history[-max_messages:] if max_messages > 0 else []


def chat_turn(
    query: str,
    history: list[dict],
    config: Settings,
    manifest: IndexManifest,
) -> ChatResponse:
    """
    Process a single chat turn with RAG.

    Args:
        query: User query
        history: Chat history (list of dicts with 'role' and 'content')
        config: Settings object
        manifest: IndexManifest

    Returns:
        ChatResponse with answer, citations, and retrieved_count
    """
    # Always retrieve - enforced at code level, not by prompt
    results = retrieve(query, config, manifest)

    # If no results, return insufficient content response
    if not results:
        return ChatResponse(
            answer=INSUFFICIENT_CONTENT_RESPONSE,
            citations=[],
            retrieved_count=0,
        )

    # Calculate input token budget
    input_token_budget = config.LLM_CONTEXT_WINDOW - config.MAX_OUTPUT_TOKENS

    # Estimate tokens for system prompt
    system_prompt_tokens = _estimate_tokens(
        "你是一个基于猫笔刀文章库回答问题的 Agent。\n"
        "你必须优先依据给定的文章片段回答。\n"
        "使用 [1]、[2] 等标记引用对应片段。\n"
        "不要把没有出现在文章片段中的内容说成猫笔刀文章观点。\n"
        "如果文章片段不足以回答，直接说明\"当前猫笔刀文章库中没有找到足够依据\"。"
    )

    # Keep only the most recent CHAT_HISTORY_TURNS * 2 valid messages
    # (user+assistant pairs), regardless of whether the budget is tight.
    max_history_messages = config.CHAT_HISTORY_TURNS * 2
    trimmed_history = _recent_valid_history(history, max_history_messages)

    # Sort by similarity so any budget trimming keeps the strongest chunks first.
    adjusted_results = sorted(results, key=lambda r: r.similarity, reverse=True)

    # Estimate tokens for retrieved chunks
    retrieved_tokens = sum(_estimate_tokens(r.chunk.text) for r in adjusted_results)

    # Estimate tokens for query
    query_tokens = _estimate_tokens(query)

    # Estimate tokens for history
    history_tokens = sum(
        _estimate_tokens(turn.get("content", "")) for turn in trimmed_history
    )

    # Total estimated tokens
    total_estimated = system_prompt_tokens + retrieved_tokens + query_tokens + history_tokens

    # If over budget, reduce chunks by removing the lowest similarity ones first.
    if total_estimated > input_token_budget:
        for keep_count in range(len(adjusted_results), 0, -1):
            test_results = adjusted_results[:keep_count]
            test_tokens = sum(_estimate_tokens(r.chunk.text) for r in test_results)
            test_total = system_prompt_tokens + test_tokens + query_tokens + history_tokens
            if test_total <= input_token_budget:
                adjusted_results = test_results
                break
        else:
            # Even one chunk doesn't fit, just use the highest similarity one
            adjusted_results = adjusted_results[:1]

    # Build prompt
    messages = build_rag_prompt(query, adjusted_results, trimmed_history)

    # Call LLM
    client = OpenAI(
        base_url=config.effective_llm_base_url,
        api_key=config.effective_llm_api_key,
    )

    response = client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=messages,
        max_tokens=config.MAX_OUTPUT_TOKENS,
    )

    answer = response.choices[0].message.content or ""

    # Generate citations
    citations = format_citations(adjusted_results)

    return ChatResponse(
        answer=answer,
        citations=citations,
        retrieved_count=len(adjusted_results),
    )
