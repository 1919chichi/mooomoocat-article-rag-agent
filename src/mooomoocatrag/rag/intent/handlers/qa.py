from __future__ import annotations

import math

from openai import OpenAI

from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChatResponse, IndexManifest
from mooomoocatrag.rag.prompt import build_rag_prompt, format_citations
from mooomoocatrag.rag.retriever import retrieve

INSUFFICIENT_CONTENT_RESPONSE = "当前猫笔刀文章库中没有找到足够依据。"

_VALID_HISTORY_ROLES = {"user", "assistant"}


def _estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / 1.5)


def _recent_valid_history(history: list[dict], max_messages: int) -> list[dict]:
    valid = [
        {"role": turn.get("role", "user"), "content": turn.get("content", "")}
        for turn in history
        if turn.get("role", "user") in _VALID_HISTORY_ROLES
    ]
    return valid[-max_messages:] if max_messages > 0 else []


def handle_qa(
    query: str,
    history: list[dict],
    config: Settings,
    manifest: IndexManifest,
) -> ChatResponse:
    results = retrieve(query, config, manifest)
    if not results:
        return ChatResponse(
            answer=INSUFFICIENT_CONTENT_RESPONSE,
            citations=[],
            retrieved_count=0,
            intent="qa",
        )

    input_token_budget = config.LLM_CONTEXT_WINDOW - config.MAX_OUTPUT_TOKENS
    system_prompt_tokens = _estimate_tokens(
        "你是一个基于猫笔刀文章库回答问题的 Agent。\n"
        "你必须优先依据给定的文章片段回答。\n"
        "使用 [1]、[2] 等标记引用对应片段。\n"
        "不要把没有出现在文章片段中的内容说成猫笔刀文章观点。\n"
        "如果文章片段不足以回答，直接说明\"当前猫笔刀文章库中没有找到足够依据\"。"
    )

    max_history_messages = config.CHAT_HISTORY_TURNS * 2
    trimmed_history = _recent_valid_history(history, max_history_messages)
    adjusted_results = sorted(results, key=lambda r: r.similarity, reverse=True)

    retrieved_tokens = sum(_estimate_tokens(r.chunk.text) for r in adjusted_results)
    query_tokens = _estimate_tokens(query)
    history_tokens = sum(_estimate_tokens(t.get("content", "")) for t in trimmed_history)
    total_estimated = system_prompt_tokens + retrieved_tokens + query_tokens + history_tokens

    if total_estimated > input_token_budget:
        for keep_count in range(len(adjusted_results), 0, -1):
            test_results = adjusted_results[:keep_count]
            test_tokens = sum(_estimate_tokens(r.chunk.text) for r in test_results)
            test_total = system_prompt_tokens + test_tokens + query_tokens + history_tokens
            if test_total <= input_token_budget:
                adjusted_results = test_results
                break
        else:
            adjusted_results = adjusted_results[:1]

    messages = build_rag_prompt(query, adjusted_results, trimmed_history)
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
    return ChatResponse(
        answer=answer,
        citations=format_citations(adjusted_results),
        retrieved_count=len(adjusted_results),
        intent="qa",
    )
